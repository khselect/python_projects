"""3성분 스튜던트 t 혼합분포 — 태그 없는 기본 모델 (PLAN.md §7.0).

과거 실적 반응(초과수익률)만으로 약세·중립·강세 시나리오의 확률·평균·척도를 추정한다.
표본이 적은 종목은 같은 산업 그룹의 적합 결과를 사전분포로 두고 MAP-EM으로 축소한다
(경험적 베이즈, 사전 가상 표본 κ = 5).

  x ~ Σ_k π_k · t_ν(μ_k, s_k),  ν 고정(기본 4)

EM (Peel & McLachlan 2000)에 사전 가상 표본을 더한 형태:
  τ_ik ∝ π_k t(x_i | μ_k, s_k)            소속 확률
  u_ik = (ν+1) / (ν + ((x_i−μ_k)/s_k)²)   꼬리 가중치 (이상치일수록 작음)
  π_k  = (Σ_i τ_ik + κ π0_k) / (n + κ)
  μ_k  = (Σ τ u x + κ π0_k μ0_k) / (Σ τ u + κ π0_k)
  s_k² = (Σ τ u (x−μ_k)² + κ π0_k s0_k²) / (Σ τ + κ π0_k)
성분은 평균 오름차순(0=약세, 1=중립, 2=강세)으로 정렬한다.

퇴화 방지
  - 척도 하한 = max(0.4%, 0.25 × 표본 표준편차): 폭이 0으로 줄어드는 "뾰족한" 성분 금지
  - 여러 시작점(분위수 3분할, 10·50·90 분위, 사전분포)에서 EM을 돌려 로그우도가 가장 큰 해 선택
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from math import lgamma, log, pi

LABELS = ("C 약세", "B 중립", "A 강세")
MIN_SCALE = 0.004
FLOOR_FRAC = 0.25


@dataclass(frozen=True)
class Mixture:
    weights: tuple[float, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    nu: float = 4.0
    n: int = 0
    loglik: float = float("nan")
    method: str = "mle"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["labels"] = list(LABELS)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Mixture":
        return cls(
            tuple(d["weights"]), tuple(d["means"]), tuple(d["scales"]),
            d.get("nu", 4.0), d.get("n", 0), d.get("loglik", float("nan")), d.get("method", "mle"),
        )


def _logpdf_t(x: np.ndarray, mu: np.ndarray, s: np.ndarray, nu: float) -> np.ndarray:
    """x: (n,1), mu·s: (k,) → (n,k)"""
    z = (x - mu) / s
    c = lgamma((nu + 1) / 2) - lgamma(nu / 2) - 0.5 * log(nu * pi)
    return c - np.log(s) - (nu + 1) / 2 * np.log1p(z * z / nu)


def _starts(x: np.ndarray, k: int) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    sd = max(float(x.std()), MIN_SCALE)
    out = []
    qs = np.quantile(x, np.linspace(0, 1, k + 1))
    mu, s = [], []
    for a, b in zip(qs[:-1], qs[1:]):
        part = x[(x >= a) & (x <= b)]
        mu.append(part.mean())
        s.append(max(part.std(), MIN_SCALE))
    out.append((np.full(k, 1 / k), np.array(mu), np.array(s)))
    out.append((np.full(k, 1 / k), np.quantile(x, np.linspace(0.1, 0.9, k)), np.full(k, sd / 2)))
    out.append((np.array([0.25, 0.5, 0.25])[:k] / np.array([0.25, 0.5, 0.25])[:k].sum(),
                np.array([x.mean() - sd, x.mean(), x.mean() + sd])[:k], np.full(k, sd / 2)))
    return out


def _em(x, w, mu, s, a, m0, s0, nu, floor, max_iter, tol):
    n = len(x)
    xc = x[:, None]
    prev = ll = -np.inf
    for _ in range(max_iter):
        lp = np.log(w) + _logpdf_t(xc, mu, s, nu)
        mx = lp.max(axis=1, keepdims=True)
        lse = mx + np.log(np.exp(lp - mx).sum(axis=1, keepdims=True))
        tau = np.exp(lp - lse)
        ll = float(lse.sum())
        z = (xc - mu) / s
        u = (nu + 1) / (nu + z * z)
        tu = tau * u
        nk = tau.sum(axis=0)
        w = (nk + a) / (n + a.sum())
        mu = ((tu * xc).sum(axis=0) + a * m0) / (tu.sum(axis=0) + a + 1e-12)
        var = ((tu * (xc - mu) ** 2).sum(axis=0) + a * s0**2) / (nk + a + 1e-12)
        s = np.maximum(np.sqrt(var), floor)
        w = np.maximum(w, 1e-4)
        w /= w.sum()
        if abs(ll - prev) < tol * max(1.0, abs(ll)):
            break
        prev = ll
    # 사전분포 로그 밀도(가상 표본) — MAP 비교용
    penalty = float(np.sum(a * np.log(w))) if a.sum() > 0 else 0.0
    return w, mu, s, ll, ll + penalty


def fit(
    x: np.ndarray,
    prior: Mixture | None = None,
    kappa: float = 5.0,
    nu: float = 4.0,
    k: int = 3,
    max_iter: int = 500,
    tol: float = 1e-9,
) -> Mixture:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < k and prior is None:
        raise ValueError(f"표본 {n}건으로는 {k}성분 적합 불가 (사전분포 필요)")

    starts = _starts(x, k) if n >= k else []
    if prior is not None:
        p0, m0, s0 = (np.array(v, dtype=float) for v in (prior.weights, prior.means, prior.scales))
        a = kappa * p0  # 성분별 가상 표본 수
        starts.insert(0, (p0.copy(), m0.copy(), s0.copy()))
        floor = max(MIN_SCALE, FLOOR_FRAC * float(np.std(np.r_[x, m0])) if n else MIN_SCALE)
    else:
        a = np.zeros(k)
        m0 = s0 = np.zeros(k)
        floor = max(MIN_SCALE, FLOOR_FRAC * float(x.std()))

    best = None
    for w0, mu0, sc0 in starts:
        res = _em(x, w0, mu0, np.maximum(sc0, floor), a, m0, s0, nu, floor, max_iter, tol)
        if best is None or res[4] > best[4]:
            best = res
    w, mu, s, ll, _ = best

    order = np.argsort(mu)
    return Mixture(
        tuple(float(v) for v in w[order]),
        tuple(float(v) for v in mu[order]),
        tuple(float(v) for v in s[order]),
        nu, n, ll, "map" if prior is not None else "mle",
    )
