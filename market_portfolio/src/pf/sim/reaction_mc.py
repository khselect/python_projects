"""실적 반응 몬테카를로 (F4·F5·F6).

1일차(반응일) 초과수익 X ~ 혼합분포 (pf.sim.mixture)
h일 누적 초과수익 CAR_h = X + Σ_{t=2..h} e_t,  e_t ~ σ_d · t_5 / √(5/3)  (단위 분산 t)
  σ_d = 실적일을 뺀 최근 252일 일별 초과수익 표준편차
  실적 후 추세(PEAD)는 MVP에서 0으로 둔다 (보수적 가정, 화면에 표시).
"""

from __future__ import annotations

import numpy as np

from pf.sim.mixture import Mixture

PCTS = (5, 25, 50, 75, 95)
DAILY_NU = 5.0
FAN_PATHS = 50_000
CHUNK = 50_000


def draw_reaction(mix: Mixture, n: int, rng: np.random.Generator) -> np.ndarray:
    cw = np.cumsum(mix.weights)
    comp = np.minimum(np.searchsorted(cw, rng.random(n) * cw[-1]), len(cw) - 1)
    mu = np.asarray(mix.means)[comp]
    s = np.asarray(mix.scales)[comp]
    return mu + s * rng.standard_t(mix.nu, n)


def summarize(x: np.ndarray, bins: int = 60) -> dict:
    q = np.percentile(x, PCTS)
    q5 = q[0]
    lo, hi = np.percentile(x, [0.5, 99.5])
    counts, edges = np.histogram(x, bins=bins, range=(lo, hi))
    return {
        "p_up": float(np.mean(x > 0)),
        "p_down": float(np.mean(x < 0)),
        "mean": float(np.mean(x)),
        "pcts": {str(p): float(v) for p, v in zip(PCTS, q)},
        "cvar5": float(np.mean(x[x <= q5])),
        "hist": {
            "edges": [round(float(e), 5) for e in edges],
            "density": [round(float(c) / len(x), 6) for c in counts],
        },
    }


def simulate(
    mix: Mixture,
    sigma_daily: float,
    n_iter: int = 400_000,
    seed: int = 0,
    horizons: tuple[int, ...] = (1, 5, 21, 63),
) -> dict:
    """반응 분포와 누적 분포 요약. 같은 입력·시드면 같은 결과."""
    rng = np.random.default_rng(seed)
    hmax = max(horizons)
    unit = sigma_daily / np.sqrt(DAILY_NU / (DAILY_NU - 2))

    x1 = draw_reaction(mix, n_iter, rng)
    term = {h: np.empty(n_iter) for h in horizons}
    term[1] = x1
    fan = None
    for start in range(0, n_iter, CHUNK):
        stop = min(start + CHUNK, n_iter)
        steps = rng.standard_t(DAILY_NU, (stop - start, hmax - 1)) * unit
        path = x1[start:stop, None] + np.concatenate(
            [np.zeros((stop - start, 1)), np.cumsum(steps, axis=1)], axis=1
        )  # (m, hmax): 열 j = (j+1)일차 누적
        for h in horizons:
            term[h][start:stop] = path[:, h - 1]
        if fan is None:
            fan = np.percentile(path[:FAN_PATHS], PCTS, axis=0)

    return {
        "n_iter": n_iter,
        "seed": seed,
        "horizons": {str(h): summarize(term[h]) for h in horizons},
        "fan": {
            "days": list(range(1, hmax + 1)),
            **{f"p{p}": [round(float(v), 5) for v in row] for p, row in zip(PCTS, fan)},
        },
        "assumptions": {
            "sigma_daily": sigma_daily,
            "daily_nu": DAILY_NU,
            "post_drift": 0.0,
        },
    }
