"""매크로 국면 → data/publish/macro.json (① 화면이 읽는 유일한 파일)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pf.config import load_model
from pf.data import store
from pf.data.fred import INTERNAL_ONLY, NOTICE, SERIES, TERMS_URL, get_fred
from pf.data.sources import Source, get_source
from pf.macro.indicators import DEFAULT_MARKET, INDICATORS, LAYER_NAME, MARKET_TICKERS as MKT_LAYER_TICKERS, compute, last_switch, regime_of
from pf.publish.ticker import PUBLISH_DIR, _write_json

MACRO_TICKERS = ["DBC", "RSP", "SPY"]
MARKET_TICKERS = ["QQQ", "OEF"]  # 국면 비교용: Nasdaq-100 · S&P 100 추종 ETF (점수 계산에는 안 씀)
MARKET_NAMES = {"QQQ": "Nasdaq-100 (QQQ)", "OEF": "S&P 100 (OEF)"}
MACRO_PATH = PUBLISH_DIR.parent / "macro.json"
COMPARE_MONTHS = (3, 6, 12)
HISTORY_YEARS = 2
EVAL_START = "2007-01-01"  # 2008 금융위기 포함 (200일선 준비 뒤 2007-10부터 평가)


def _f(v):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), 5)


def _values(row: pd.Series, key: str) -> dict:
    """화면 표시용 수치. 내부 전용(신용)은 값 대신 방향만."""
    pre = f"val_{key}_"
    vals = {c[len(pre):]: _f(row[c]) for c in row.index if c.startswith(pre)}
    if key == "curve":
        vals["level"] = _f(row["val_curve"])
    if key == "vix":
        vals.pop("level", None)
        vals["level"] = _f(row["val_vix_level"])
    if key == "credit":
        d = vals.pop("d3m", None)
        vals = {"direction": None if d is None else ("축소" if d <= 0 else "확대")}
    return vals


def _stress(row: pd.Series) -> bool:
    return bool(row.get("stress", 0) == 1)


def _regimes(df: pd.DataFrame, hi: int, lo: int) -> pd.Series:
    st = df["stress"] if "stress" in df else pd.Series(0.0, index=df.index)
    return pd.Series([regime_of(s, hi, lo, x == 1) for s, x in zip(df["score"], st)], index=df.index)


def _snapshot(df: pd.DataFrame, at: pd.Timestamp, hi: int, lo: int) -> dict:
    pos = df.index.searchsorted(at, side="right") - 1
    row = df.iloc[max(pos, 0)]
    return {
        "date": df.index[max(pos, 0)].date().isoformat(),
        "score": int(row["score"]),
        "regime": regime_of(row["score"], hi, lo, _stress(row)),
        "signals": {i.key: _f(row[f"sig_{i.key}"]) for i in INDICATORS},
    }


def markets(prices: pd.DataFrame, start: pd.Timestamp) -> dict | None:
    """국면 점수 추이와 같은 기간·주간 간격의 지수 비교. 시작 주 = 100, QQQ/OEF 비율도 시작 = 100.

    S0(비공개)용 — Yahoo 시세 파생이라 공개(S1) 전에는 라이선스 데이터로 바꾸거나 국면별 평균 수익률로 대체.
    """
    cols = [t for t in MARKET_TICKERS if t in prices and prices[t].notna().sum() > 0]
    if len(cols) < 2:
        return None
    w = prices.loc[prices.index >= start, cols].resample("W-FRI").last().dropna()
    if len(w) < 2:
        return None
    idx = w / w.iloc[0] * 100
    ratio = (w["QQQ"] / w["OEF"]) / (w["QQQ"].iloc[0] / w["OEF"].iloc[0]) * 100
    return {
        "dates": [d.date().isoformat() for d in w.index],
        "names": MARKET_NAMES,
        "series": {t: [round(float(v), 2) for v in idx[t]] for t in cols},
        "ratio": [round(float(v), 2) for v in ratio],
        "change": {t: round(float(idx[t].iloc[-1] / 100 - 1), 4) for t in cols},
    }


def build(df: pd.DataFrame, source_name: str, hi: int = 4, lo: int = -4, prices: pd.DataFrame | None = None,
          market_cfg: dict | None = None) -> dict:
    asof = df.index[-1]
    last = df.iloc[-1]
    reg = _regimes(df, hi, lo)
    since = reg[reg.ne(reg.shift())].index[-1]
    hist = df[df.index >= asof - pd.DateOffset(years=HISTORY_YEARS)]
    wk = hist.resample("W-FRI").last().dropna(subset=["score"])
    indicators = []
    for ind in INDICATORS:
        indicators.append({
            "key": ind.key,
            "name": ind.name,
            "layer": ind.layer,
            "public_values": ind.public,
            "signal": _f(last[f"sig_{ind.key}"]),
            "raw": _f(last[f"raw_{ind.key}"]),
            "last_switch": last_switch(df[f"sig_{ind.key}"]),
            "values": _values(last, ind.key),
        })
    st_on = _stress(last)
    mc = {**DEFAULT_MARKET, **(market_cfg or {})}
    since_on = None
    if st_on:
        off = df.index[df["stress"] != 1]
        since_on = (df.index[df.index > off[-1]][0] if len(off) else df.index[0]).date().isoformat()
    stress = {
        "on": st_on,
        "since": since_on,
        "entry_today": bool(last.get("stress_entry", 0) == 1),
        "vix": bool(last.get("stress_vix", 0) == 1),
        "ndx_dd": bool(last.get("stress_dd", 0) == 1),
        "calm_run": int(last.get("stress_calm_run", 0) or 0),
        "rule": f"진입: VIX ≥ {mc['stress_vix']} 또는 나스닥100 고점 대비 {mc['stress_ndx_dd'] * 100:.0f}% 이하 (즉시)",
        "exit_rule": f"해제: VIX < {mc['stress_exit_vix']} 이고 나스닥100 고점 대비 {mc['stress_exit_ndx_dd'] * 100:.0f}%보다 회복이 "
                     f"{mc['stress_exit_days']}거래일 연속",
        "exit_days": int(mc["stress_exit_days"]),
    }
    n_layer = {k: sum(1 for i in INDICATORS if i.layer == k) for k in LAYER_NAME}
    return {
        "schema": 2,
        "asof": asof.date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source_name,
        "score": int(last["score"]),
        "score_range": len(INDICATORS),
        "layers": {k: {"name": LAYER_NAME[k], "score": int(last[f"score_{k}"]), "n": n_layer[k],
                       "confirm_days": 5 if k == "macro" else int((market_cfg or {}).get("confirm_days", 2))}
                   for k in LAYER_NAME},
        "n_signals": int(last["n_signals"]),
        "regime": regime_of(last["score"], hi, lo, st_on),
        "regime_since": since.date().isoformat(),
        "stress": stress,
        "thresholds": {"expansion": hi, "riskoff": lo},
        "neutral_bands": True,
        "indicators": indicators,
        "compare": {str(m): _snapshot(df, asof - pd.DateOffset(months=m), hi, lo) for m in COMPARE_MONTHS},
        "history": {
            "dates": [d.date().isoformat() for d in wk.index],
            "score": [int(v) for v in wk["score"]],
            "macro": [int(v) for v in wk["score_macro"]],
            "market": [int(v) for v in wk["score_market"]],
            "stress": [bool(v == 1) for v in wk.get("stress", pd.Series(0, index=wk.index))],
        },
        "markets": markets(prices, wk.index[0] - pd.Timedelta(days=6)) if prices is not None and len(wk) else None,
        "notice": {"fred": NOTICE, "terms_url": TERMS_URL, "internal_only": sorted(INTERNAL_ONLY)},
    }


def frame(source: Source, fred, cfg: dict, start: str = "2012-01-01",
          prices: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """원천 수집 → 지표 계산. (지표 DataFrame, 시세). 검증(pf.macro.evaluate)도 같은 경로를 쓴다."""
    need = MACRO_TICKERS + MARKET_TICKERS + list(MKT_LAYER_TICKERS)
    if prices is None or not set(need) <= set(prices.columns):
        prices = source.prices(need, start=start)
    series = fred.frame(list(SERIES), start=start)
    base = prices[MACRO_TICKERS].dropna()
    mkt = prices.reindex(columns=list(MKT_LAYER_TICKERS)).reindex(base.index).ffill(limit=5)
    df = compute(base.join(mkt), series, cfg.get("neutral"), cfg.get("market"))
    return df, prices, series


def publish_macro(source: Source | None = None, fred=None, prices: pd.DataFrame | None = None) -> Path:
    cfg = load_model()["macro"]
    source = source or get_source()
    fred = fred or get_fred()
    # 2007년부터 계산: 화면은 최근 2년만 쓰지만, 같은 계산으로 스트레스 구간 검증(macro_eval.json)도 남긴다
    df, prices, series = frame(source, fred, cfg, start=EVAL_START, prices=prices)
    try:
        from pf.macro.evaluate import publish_eval

        publish_eval(source=source, fred=fred, df=df, prices=prices)
    except Exception:  # 검증 실패가 국면 게시를 막지 않게
        pass
    for k, s in series.items():
        store.save_prices(f"{fred.name}_{k}", s.to_frame(k))
    payload = build(df, f"{source.name}+{fred.name}", cfg["regime_expansion_min"], cfg["regime_riskoff_max"], prices,
                    {**DEFAULT_MARKET, **(cfg.get("market") or {})})
    MACRO_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(MACRO_PATH, payload, separators=(",", ":"))
    return MACRO_PATH
