"""매크로 국면 판정 (PLAN.md §7.5, F16) — 두 속도 국면 점수 (v0.21, 11-27).

10개 지표를 매 거래일 위험자산 우호(+1)·중립(0)·비우호(−1)로 판정하고 더해 국면 점수(−10~+10)를 만든다.
  매크로 층(느림, 6개): 원 신호가 5거래일 연속 유지돼야 전환 (깜빡임 방지)
  시장 층(빠름, 4개):  VIX · 추세·낙폭 · 섹터 폭 · 단기금리 변동, 2거래일 확정
중립 구간은 config/model.yaml macro.neutral / macro.market.
급변 규칙: VIX ≥ 30 또는 나스닥100 고점 대비 −20% 이하면 점수와 관계없이 "위험회피(급변)" (확정 기간 없음).

v0.20까지는 매크로 층 6개만 있어 주가·변동성을 직접 보는 지표가 없었다 → 나스닥 급락·VIX 급등에도
점수 0이 나올 수 있었다(11-26 운영에서 확인). 시장 층을 더하고 경계를 ±3/6 → ±4/10으로 옮겼다.

| 지표     | +1 (우호)                                    | 0 (중립)                         | −1 (비우호)                                   |
|----------|----------------------------------------------|----------------------------------|-----------------------------------------------|
| 유동성   | 갭 ≥ 0.5%p, 6개월 금리 동결·인하, 갭 급축소 없음 | 갭 0~0.5%p (그 외 조건 충족)       | 갭 ≤ 0, 6개월 금리 인상, 갭 0.5%p 넘게 축소      |
| 원자재   | DBC가 200일선 +1% 위                          | 200일선 ±1%                       | 200일선 −1% 아래                               |
| 시장 폭  | RSP/SPY가 200일선 +1% 위, 괴리 없음            | 200일선 ±1%                       | 200일선 −1% 아래 또는 괴리                       |
| 신용     | 하이일드 스프레드 3개월 −0.10%p 넘게 축소        | 3개월 변화 ±0.10%p                | 3개월 +0.10%p 넘게 확대                         |
| 금리곡선 | 10Y−2Y ≥ 0.25%p, 마지막 역전 후 182일 이상      | 0~0.25%p, 역전 후 182일 이상        | 역전 중 또는 역전 해소 후 182일 이내              |
| 달러     | 광의 달러지수가 200일선 −1% 아래, 6개월 +3% 미만 | 200일선 ±1%, 6개월 +3% 미만        | 200일선 +1% 위 또는 6개월 +3% 이상               |

괴리: SPY가 52주 고점 3% 이내인데 RSP/SPY는 고점 대비 −5% 이하 (소수 대형주만 오르는 상승).
GDP는 분기 말 약 30일 뒤 발표 → 발표일 기준으로만 반영(미래 정보 누수 방지).
신용 시리즈는 FRED에 최근 3년만 있어, 그 이전은 신호 없음(점수 0 기여)으로 둔다.
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
    layer: str = "macro"  # macro(느림, 5일 확정) | market(빠름, 2일 확정)


MACRO_INDICATORS = (
    Indicator("liquidity", "유동성"),
    Indicator("commodity", "원자재"),
    Indicator("breadth", "시장 폭"),
    Indicator("credit", "신용", public=False),
    Indicator("curve", "금리곡선"),
    Indicator("dollar", "달러"),
)
MARKET_INDICATORS = (
    Indicator("vix", "VIX", layer="market"),
    Indicator("trend", "추세·낙폭", layer="market"),
    Indicator("sectors", "섹터 폭", layer="market"),
    Indicator("rates", "단기금리 변동", layer="market"),
)
INDICATORS = MACRO_INDICATORS + MARKET_INDICATORS
LAYER_NAME = {"macro": "매크로 층", "market": "시장 층"}

VIX, SPX, NDX = "^VIX", "^GSPC", "^NDX"
SECTORS = ("XLK", "XLC", "XLY", "XLF", "XLV", "XLI", "XLE", "XLB", "XLP", "XLU", "XLRE")
MARKET_TICKERS = (VIX, SPX, NDX) + SECTORS
STRESS_LABEL = "위험회피(급변)"


def regime_of(score: float, hi: int = 4, lo: int = -4, stress: bool = False) -> str:
    if stress:
        return STRESS_LABEL
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


DEFAULT_NEUTRAL = {"ma_band": 0.01, "liquidity_gap": 0.5, "credit_d3m": 0.10, "curve_flat": 0.25}
DEFAULT_MARKET = {
    "confirm_days": 2,
    "vix": [17, 25],                       # 미만 우호 / 이상 비우호
    "trend_ok_dd": -0.05,                  # 두 지수 모두 200일선 위이고 고점 대비 이 이내 → 우호
    "trend_bad_dd": -0.10,                 # 어느 한 지수라도 200일선 아래 또는 이 이하 → 비우호
    "sectors": [0.40, 0.60],               # 200일선 위 섹터 비율: 미만 비우호 / 이상 우호
    "sectors_min": 8,                      # 계산에 필요한 최소 섹터 수 (XLC 2018~, XLRE 2015~)
    "rates_calm": 0.10,                    # 2년물 21거래일 변화 |Δ| ≤ 0.10%p → 우호(안정)
    "rates_up": 0.25,                      # Δ ≥ +0.25%p → 비우호(긴축 쇼크)
    "rates_down": -0.50,                   # Δ ≤ −0.50%p → 비우호(위기성 급락, 안전자산 쏠림)
    "stress_vix": 30,
    "stress_ndx_dd": -0.20,
}


def _sign(cond: pd.Series, valid: pd.Series) -> pd.Series:
    return pd.Series(np.where(cond, 1.0, -1.0), index=cond.index).where(valid)


def _tri(pos: pd.Series, neg: pd.Series, valid: pd.Series) -> pd.Series:
    """neg가 우선: neg → −1, pos → +1, 둘 다 아니면 0 (중립)."""
    out = np.where(neg, -1.0, np.where(pos, 1.0, 0.0))
    return pd.Series(out, index=valid.index).where(valid)


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


def _market_layer(df: pd.DataFrame, prices: pd.DataFrame, fred: dict[str, pd.Series], mk: dict) -> None:
    """시장 층 4개 (빠름). 입력이 없으면 그 지표는 신호 없음(NaN)."""
    idx = df.index
    col = lambda t: prices[t] if t in prices else pd.Series(np.nan, index=idx)  # noqa: E731

    # VIX
    vix = col(VIX)
    lo, hi = mk["vix"]
    df["val_vix_level"] = vix
    df["val_vix_max_1m"] = vix.rolling(21, min_periods=1).max()
    df["raw_vix"] = _tri(vix < lo, vix >= hi, vix.notna())

    # 추세·낙폭: S&P 500, 나스닥100
    above, dd = {}, {}
    for t, k in ((SPX, "spx"), (NDX, "ndx")):
        px = col(t)
        ma = px.rolling(MA).mean()
        df[f"val_trend_{k}_vs_ma"] = px / ma - 1
        dd[k] = px / px.rolling(D1Y, min_periods=MA).max() - 1
        df[f"val_trend_{k}_dd"] = dd[k]
        above[k] = px > ma
    ok = df["val_trend_spx_vs_ma"].notna() & df["val_trend_ndx_vs_ma"].notna() & dd["spx"].notna() & dd["ndx"].notna()
    pos = above["spx"] & above["ndx"] & (dd["spx"] > mk["trend_ok_dd"]) & (dd["ndx"] > mk["trend_ok_dd"])
    neg = ~above["spx"] | ~above["ndx"] | (dd["spx"] <= mk["trend_bad_dd"]) | (dd["ndx"] <= mk["trend_bad_dd"])
    df["raw_trend"] = _tri(pos, neg, ok)

    # 섹터 폭: 200일선 위 섹터 비율
    secs = [t for t in SECTORS if t in prices]
    if secs:
        px = prices[secs]
        ma = px.rolling(MA).mean()
        valid = ma.notna()
        n = valid.sum(axis=1)
        share = ((px > ma) & valid).sum(axis=1) / n.where(n > 0)
    else:
        n, share = pd.Series(0, index=idx), pd.Series(np.nan, index=idx)
    df["val_sectors_share"], df["val_sectors_n"] = share, n.astype(float)
    s_lo, s_hi = mk["sectors"]
    df["raw_sectors"] = _tri(share >= s_hi, share < s_lo, share.notna() & (n >= mk["sectors_min"]))

    # 단기금리 변동: 2년물 21거래일 변화
    if "DGS2" in fred:
        y2 = fred["DGS2"].reindex(idx.union(fred["DGS2"].index)).ffill().reindex(idx)
    else:
        y2 = pd.Series(np.nan, index=idx)
    d21 = y2 - y2.shift(21)
    df["val_rates_y2"], df["val_rates_d1m"] = y2, d21
    df["raw_rates"] = _tri(d21.abs() <= mk["rates_calm"], (d21 >= mk["rates_up"]) | (d21 <= mk["rates_down"]), d21.notna())

    # 급변 (확정 기간 없음)
    stress_vix = vix >= mk["stress_vix"]
    stress_dd = dd["ndx"] <= mk["stress_ndx_dd"]
    df["stress_vix"], df["stress_dd"] = stress_vix.astype(float), stress_dd.astype(float)
    df["stress"] = (stress_vix | stress_dd).astype(float)


def compute(prices: pd.DataFrame, fred: dict[str, pd.Series], neutral: dict | None = None,
            market: dict | None = None) -> pd.DataFrame:
    """prices: DBC·RSP·SPY(+ 시장 층: ^VIX·^GSPC·^NDX·섹터 ETF) 수정 종가(거래일 index).
    fred: SERIES 키별 시계열. neutral: 매크로 층 중립 구간. market: 시장 층 경계."""
    nb = {**DEFAULT_NEUTRAL, **(neutral or {})}
    mk = {**DEFAULT_MARKET, **(market or {})}
    band = nb["ma_band"]
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
    liq_ok = gap.notna() & d_rate.notna() & d_gap.notna()
    liq_neg = (gap <= 0) | (d_rate > 0) | (d_gap < -0.5)
    df["raw_liquidity"] = _tri(gap >= nb["liquidity_gap"], liq_neg, liq_ok)

    # 원자재
    dbc = prices["DBC"]
    ma = dbc.rolling(MA).mean()
    c_ma = dbc / ma - 1
    df["val_commodity_vs_ma"] = c_ma
    df["val_commodity_vs_high"] = dbc / dbc.rolling(D1Y).max() - 1
    df["raw_commodity"] = _tri(c_ma > band, c_ma < -band, ma.notna())

    # 시장 폭
    ratio = prices["RSP"] / prices["SPY"]
    rma = ratio.rolling(MA).mean()
    spy_hi = prices["SPY"] / prices["SPY"].rolling(D1Y).max() - 1
    r_hi = ratio / ratio.rolling(D1Y).max() - 1
    diverge = (spy_hi >= -0.03) & (r_hi <= -0.05)
    b_ma = ratio / rma - 1
    df["val_breadth_vs_ma"], df["val_breadth_vs_high"], df["val_breadth_spy_vs_high"] = b_ma, r_hi, spy_hi
    df["val_breadth_divergence"] = diverge.astype(float)
    df["raw_breadth"] = _tri(b_ma > band, (b_ma < -band) | diverge, rma.notna() & r_hi.notna())

    # 신용 (값은 내부 전용)
    hy = on(fred["BAMLH0A0HYM2"])
    hy = hy.where(idx >= fred["BAMLH0A0HYM2"].dropna().index.min()) if fred["BAMLH0A0HYM2"].notna().any() else hy * np.nan
    d_hy = hy - hy.shift(D3M)
    df["val_credit_d3m"] = d_hy
    df["raw_credit"] = _tri(d_hy < -nb["credit_d3m"], d_hy > nb["credit_d3m"], d_hy.notna())

    # 금리곡선
    curve = on(fred["T10Y2Y"])
    since = days_since_inversion(curve)
    df["val_curve"], df["val_curve_days_since_inv"] = curve, since
    df["raw_curve"] = _tri(curve >= nb["curve_flat"], (curve < 0) | (since < 182), curve.notna())

    # 달러
    usd = on(fred["DTWEXBGS"])
    uma = usd.rolling(MA, min_periods=150).mean()
    u6 = usd / usd.shift(D6M) - 1
    d_ma = usd / uma - 1
    df["val_dollar_vs_ma"], df["val_dollar_6m"] = d_ma, u6
    df["raw_dollar"] = _tri(d_ma < -band, (d_ma > band) | (u6 >= 0.03), uma.notna() & u6.notna())

    _market_layer(df, prices, fred, mk)

    for ind in INDICATORS:
        days = CONFIRM_DAYS if ind.layer == "macro" else int(mk["confirm_days"])
        df[f"sig_{ind.key}"] = confirm(df[f"raw_{ind.key}"], days)
    sigs = df[[f"sig_{i.key}" for i in INDICATORS]]
    df["n_signals"] = sigs.notna().sum(axis=1)
    for layer in ("macro", "market"):
        df[f"score_{layer}"] = df[[f"sig_{i.key}" for i in INDICATORS if i.layer == layer]].fillna(0).sum(axis=1)
    df["score"] = sigs.fillna(0).sum(axis=1)
    return df


def last_switch(sig: pd.Series) -> str | None:
    """확정 신호가 마지막으로 바뀐 날짜 (처음 생긴 날 제외)."""
    s = sig.dropna()
    ch = s[s.ne(s.shift())].index[1:]
    return ch[-1].date().isoformat() if len(ch) else None
