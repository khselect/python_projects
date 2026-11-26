"""실적 이벤트 → 반응일·초과수익률 (PLAN.md §7.0, §7.2).

반응일
  장후(AMC) 발표 → 발표일 다음 거래일
  장전(BMO) 발표 → 발표일 당일
  시각 모름(UNK) → 장후로 간주 (미국 대형주 다수가 장후 발표. 보수적으로 표시만 남김)

초과수익률 (베타 조정)
  AR_t = R_t − β · R_bench,t
  β: 반응일 5거래일 전까지 252거래일 일수익률 회귀, [0, 3]로 제한
  CAR_h = 반응일(1일차)부터 h거래일 AR 합  (h = 1, 5, 21, 63)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BETA_WINDOW = 252
BETA_GAP = 5
HORIZONS = (1, 5, 21, 63)


def reaction_index(days: pd.DatetimeIndex, date: pd.Timestamp, timing: str) -> int | None:
    """반응일의 위치. 데이터 범위 밖이면 None."""
    date = pd.Timestamp(date).normalize()
    if timing == "BMO":
        pos = days.searchsorted(date, side="left")  # 당일(휴장이면 다음 거래일)
    else:
        pos = days.searchsorted(date, side="right")  # 다음 거래일
    return int(pos) if 0 < pos < len(days) else None


def _beta(r: np.ndarray, m: np.ndarray) -> float:
    ok = np.isfinite(r) & np.isfinite(m)
    if ok.sum() < 60:
        return 1.0
    r, m = r[ok], m[ok]
    var = np.var(m)
    if var <= 0:
        return 1.0
    return float(np.clip(np.cov(r, m, bias=True)[0, 1] / var, 0.0, 3.0))


def build_reactions(
    prices: pd.Series,
    bench: pd.Series,
    earnings: pd.DataFrame,
    horizons: tuple[int, ...] = HORIZONS,
) -> pd.DataFrame:
    """과거 실적 이벤트별 반응 표. 반응일 이후 데이터가 모자란 구간은 NaN."""
    px = pd.concat([prices.rename("p"), bench.rename("b")], axis=1).dropna()
    days = px.index
    ret = px.pct_change()
    r, m = ret["p"].to_numpy(), ret["b"].to_numpy()

    rows = []
    for ev in earnings.itertuples(index=False):
        j = reaction_index(days, ev.date, ev.timing)
        if j is None or j < BETA_WINDOW + BETA_GAP:
            continue
        lo, hi = j - BETA_GAP - BETA_WINDOW, j - BETA_GAP
        beta = _beta(r[lo:hi], m[lo:hi])
        row = {
            "event_date": pd.Timestamp(ev.date).date().isoformat(),
            "timing": ev.timing,
            "reaction_date": days[j].date().isoformat(),
            "beta": round(beta, 3),
            "ret1": float(r[j]),
        }
        for h in horizons:
            end = j + h
            row[f"car{h}"] = (
                float(np.sum(r[j:end] - beta * m[j:end])) if end <= len(days) else np.nan
            )
        for k in ("eps_est", "eps_act", "surprise_pct"):
            v = getattr(ev, k)
            row[k] = None if pd.isna(v) else float(v)
        rows.append(row)
    return pd.DataFrame(rows)


def next_event(earnings: pd.DataFrame, asof: pd.Timestamp) -> dict | None:
    """기준일 이후 첫 실적 예정일."""
    fut = earnings[pd.to_datetime(earnings["date"]) > pd.Timestamp(asof)]
    if fut.empty:
        return None
    ev = fut.sort_values("date").iloc[0]
    return {"date": pd.Timestamp(ev["date"]).date().isoformat(), "timing": ev["timing"]}


def daily_excess_sigma(
    prices: pd.Series, bench: pd.Series, reactions: pd.DataFrame, window: int = 252
) -> tuple[float, float]:
    """실적 반응일을 뺀 최근 window일 초과수익률의 (β, 표준편차). 누적 분포의 비이벤트일 변동성."""
    px = pd.concat([prices.rename("p"), bench.rename("b")], axis=1).dropna()
    ret = px.pct_change().dropna().iloc[-window:]
    beta = _beta(ret["p"].to_numpy(), ret["b"].to_numpy())
    ex = ret["p"] - beta * ret["b"]
    if len(reactions):
        ex = ex.drop(pd.to_datetime(reactions["reaction_date"]), errors="ignore")
    return beta, float(ex.std(ddof=1))
