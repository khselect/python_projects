"""매크로 국면 판정 (PLAN.md §7.5, F16).

6개 지표를 매 거래일 위험자산 우호(+1)·비우호(−1)로 판정하고 더해 국면 점수(−6~+6)를 만든다.
수준보다 방향 전환을 본다. 원 신호가 5거래일 연속 유지돼야 전환으로 인정한다(깜빡임 방지).

| 지표     | +1 (우호)                                         | −1 (비우호)                                    |
|----------|---------------------------------------------------|------------------------------------------------|
| 유동성   | GDP 전년비 − 기준금리 > 0, 6개월 금리 동결·인하,    | 그 외 (갭 ≤ 0, 금리 인상, 갭 0.5%p 이상 축소)    |
|          | 갭이 6개월간 0.5%p 넘게 줄지 않음                   |                                                |
| 원자재   | DBC > 200일선                                     | DBC ≤ 200일선                                  |
| 시장 폭  | RSP/SPY > 200일선, 괴리 없음                       | RSP/SPY ≤ 200일선 또는 괴리                     |
|          |                                                   | (SPY 52주 고점 3% 이내인데 RSP/SPY 고점 대비 −5%↓) |
| 신용     | 하이일드 스프레드 3개월 변화 ≤ 0 (축소)            | 3개월 확대                                      |
| 금리곡선 | 10Y−2Y > 0 이고 마지막 역전 후 182일 이상           | 역전 중 또는 역전 해소 후 182일 이내              |
| 달러     | 광의 달러지수 ≤ 200일선 이고 6개월 +3% 미만        | 200일선 위 또는 6개월 +3% 이상                   |

시장 폭은 "RSP/SPY 신고가 동반"을 200일선 위로 근사한다.
GDP는 분기 말 약 30일 뒤 발표 → 발표일 기준으로만 반영(미래 정보 누수 방지).
신용 시리즈는 FRED에 최근 3년만 있어, 그 이전은 신호 없음(0)으로 두고 표시한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CONFIRM_DAYS = 5
D6M, D3M, D1Y, MA = 126, 63, 252, 200


@dataclass(frozen=True)
class Indicator:
    key: str
    name: str
    public: bool = True  # False면 값은 화면에 내지 않고 신호만 (라이선스)


INDICATORS = (
    Indicator("liquidity", "유동성"),
    Indicator("commodity", "원자재"),
    Indicator("breadth", "시장 폭"),
    Indicator("credit", "신용", public=False),
    Indicator("curve", "금리곡선"),
    Indicator("dollar", "달러"),
)


def regime_of(score: float, hi: int = 3, lo: int = -3) -> str:
    if score >= hi:
        return "확장"
    if score <= lo:
        return "위험회피"
    return "중립·전환"


def confirm(raw: pd.Series, days: int = CONFIRM_DAYS) -> pd.Series:
    """원 신호가 days 거래일 연속 같은 값일 때만 확정 신호를 바꾼다. NaN은 신호 없음(유지 끊김)."""
    out = np.full(len(raw), np.nan)
    cur, cand, run = np.nan, np.nan, 0
    for i, v in enumerate(raw.to_numpy()):
        if np.isnan(v):
            cand, run = np.nan, 0
            cur = np.nan if np.isnan(cur) else cur
        elif np.isnan(cur):
            cand, run = (v, run + 1) if v == cand else (v, 1)
            if run >= days:
                cur = v
        elif v == cur:
            cand, run = np.nan, 0
        else:
            cand, run = (v, run + 1) if v == cand else (v, 1)
            if run >= days:
                cur = v
        out[i] = cur
    return pd.Series(out, index=raw.index)


def _sign(cond: pd.Series, valid: pd.Series) -> pd.Series:
    return pd.Series(np.where(cond, 1.0, -1.0), index=cond.index).where(valid)


def gdp_yoy_available(gdp: pd.Series, lag_days: int = 30) -> pd.Series:
    """분기 GDP 전년비(%)를 발표 추정일(분기 말 + lag_days)에 배치."""
    q = gdp.dropna()
    yoy = (q / q.shift(4) - 1) * 100
    avail = q.index + pd.offsets.QuarterEnd(0) + pd.Timedelta(days=lag_days)
    return pd.Series(yoy.to_numpy(), index=avail).dropna()


def days_since_inversion(curve: pd.Series) -> pd.Series:
    """각 날짜 기준 마지막 역전(<0)일로부터 지난 달력일. 역전 이력이 없으면 큰 값."""
    last = curve.index.to_series().where(curve < 0).ffill()
    d = (curve.index.to_series() - last).dt.days
    return d.fillna(10_000).where(curve.notna())


def compute(prices: pd.DataFrame, fred: dict[str, pd.Series]) -> pd.DataFrame:
    """prices: DBC·RSP·SPY 수정 종가(거래일 index). fred: SERIES 키별 시계열."""
    idx = prices.index
    on = lambda s: s.reindex(idx.union(s.index)).ffill().reindex(idx)  # noqa: E731
    df = pd.DataFrame(index=idx)

    # 유동성
    rate = on(fred["DFEDTARU"])
    gdp = on(gdp_yoy_available(fred["GDP"]))
    gap = gdp - rate
    d_rate = rate - rate.shift(D6M)
    d_gap = gap - gap.shift(D6M)
    df["val_liquidity_gdp"], df["val_liquidity_rate"] = gdp, rate
    df["val_liquidity_gap"], df["val_liquidity_drate6m"], df["val_liquidity_dgap6m"] = gap, d_rate, d_gap
    df["raw_liquidity"] = _sign((gap > 0) & (d_rate <= 0) & (d_gap >= -0.5), gap.notna() & d_rate.notna() & d_gap.notna())

    # 원자재
    dbc = prices["DBC"]
    ma = dbc.rolling(MA).mean()
    df["val_commodity_vs_ma"] = dbc / ma - 1
    df["val_commodity_vs_high"] = dbc / dbc.rolling(D1Y).max() - 1
    df["raw_commodity"] = _sign(dbc > ma, ma.notna())

    # 시장 폭
    ratio = prices["RSP"] / prices["SPY"]
    rma = ratio.rolling(MA).mean()
    spy_hi = prices["SPY"] / prices["SPY"].rolling(D1Y).max() - 1
    r_hi = ratio / ratio.rolling(D1Y).max() - 1
    diverge = (spy_hi >= -0.03) & (r_hi <= -0.05)
    df["val_breadth_vs_ma"], df["val_breadth_vs_high"], df["val_breadth_spy_vs_high"] = ratio / rma - 1, r_hi, spy_hi
    df["val_breadth_divergence"] = diverge.astype(float)
    df["raw_breadth"] = _sign((ratio > rma) & ~diverge, rma.notna() & r_hi.notna())

    # 신용 (값은 내부 전용)
    hy = on(fred["BAMLH0A0HYM2"])
    hy = hy.where(idx >= fred["BAMLH0A0HYM2"].dropna().index.min()) if fred["BAMLH0A0HYM2"].notna().any() else hy * np.nan
    d_hy = hy - hy.shift(D3M)
    df["val_credit_d3m"] = d_hy
    df["raw_credit"] = _sign(d_hy <= 0, d_hy.notna())

    # 금리곡선
    curve = on(fred["T10Y2Y"])
    since = days_since_inversion(curve)
    df["val_curve"], df["val_curve_days_since_inv"] = curve, since
    df["raw_curve"] = _sign((curve > 0) & (since >= 182), curve.notna())

    # 달러
    usd = on(fred["DTWEXBGS"])
    uma = usd.rolling(MA, min_periods=150).mean()
    u6 = usd / usd.shift(D6M) - 1
    df["val_dollar_vs_ma"], df["val_dollar_6m"] = usd / uma - 1, u6
    df["raw_dollar"] = _sign((usd <= uma) & (u6 < 0.03), uma.notna() & u6.notna())

    for ind in INDICATORS:
        df[f"sig_{ind.key}"] = confirm(df[f"raw_{ind.key}"])
    sigs = df[[f"sig_{i.key}" for i in INDICATORS]]
    df["n_signals"] = sigs.notna().sum(axis=1)
    df["score"] = sigs.fillna(0).sum(axis=1)
    return df


def last_switch(sig: pd.Series) -> str | None:
    """확정 신호가 마지막으로 바뀐 날짜 (처음 생긴 날 제외)."""
    s = sig.dropna()
    ch = s[s.ne(s.shift())].index[1:]
    return ch[-1].date().isoformat() if len(ch) else None
