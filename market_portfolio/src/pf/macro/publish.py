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
from pf.macro.indicators import INDICATORS, compute, last_switch, regime_of
from pf.publish.ticker import PUBLISH_DIR, _write_json

MACRO_TICKERS = ["DBC", "RSP", "SPY"]
MARKET_TICKERS = ["QQQ", "OEF"]  # 국면 비교용: Nasdaq-100 · S&P 100 추종 ETF (점수 계산에는 안 씀)
MARKET_NAMES = {"QQQ": "Nasdaq-100 (QQQ)", "OEF": "S&P 100 (OEF)"}
MACRO_PATH = PUBLISH_DIR.parent / "macro.json"
COMPARE_MONTHS = (3, 6, 12)
HISTORY_YEARS = 2


def _f(v):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), 5)


def _values(row: pd.Series, key: str) -> dict:
    """화면 표시용 수치. 내부 전용(신용)은 값 대신 방향만."""
    pre = f"val_{key}_"
    vals = {c[len(pre):]: _f(row[c]) for c in row.index if c.startswith(pre)}
    if key == "curve":
        vals["level"] = _f(row["val_curve"])
    if key == "credit":
        d = vals.pop("d3m", None)
        vals = {"direction": None if d is None else ("축소" if d <= 0 else "확대")}
    return vals


def _snapshot(df: pd.DataFrame, at: pd.Timestamp, hi: int, lo: int) -> dict:
    pos = df.index.searchsorted(at, side="right") - 1
    row = df.iloc[max(pos, 0)]
    return {
        "date": df.index[max(pos, 0)].date().isoformat(),
        "score": int(row["score"]),
        "regime": regime_of(row["score"], hi, lo),
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


def build(df: pd.DataFrame, source_name: str, hi: int = 3, lo: int = -3, prices: pd.DataFrame | None = None) -> dict:
    asof = df.index[-1]
    last = df.iloc[-1]
    reg = df["score"].map(lambda s: regime_of(s, hi, lo))
    since = reg[reg.ne(reg.shift())].index[-1]
    hist = df[df.index >= asof - pd.DateOffset(years=HISTORY_YEARS)]
    weekly = hist["score"].resample("W-FRI").last().dropna()
    indicators = []
    for ind in INDICATORS:
        indicators.append({
            "key": ind.key,
            "name": ind.name,
            "public_values": ind.public,
            "signal": _f(last[f"sig_{ind.key}"]),
            "raw": _f(last[f"raw_{ind.key}"]),
            "last_switch": last_switch(df[f"sig_{ind.key}"]),
            "values": _values(last, ind.key),
        })
    return {
        "schema": 1,
        "asof": asof.date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source_name,
        "score": int(last["score"]),
        "n_signals": int(last["n_signals"]),
        "regime": regime_of(last["score"], hi, lo),
        "regime_since": since.date().isoformat(),
        "thresholds": {"expansion": hi, "riskoff": lo},
        "neutral_bands": True,
        "indicators": indicators,
        "compare": {str(m): _snapshot(df, asof - pd.DateOffset(months=m), hi, lo) for m in COMPARE_MONTHS},
        "history": {"dates": [d.date().isoformat() for d in weekly.index], "score": [int(v) for v in weekly]},
        "markets": markets(prices, weekly.index[0] - pd.Timedelta(days=6)) if prices is not None and len(weekly) else None,
        "notice": {"fred": NOTICE, "terms_url": TERMS_URL, "internal_only": sorted(INTERNAL_ONLY)},
    }


def publish_macro(source: Source | None = None, fred=None, prices: pd.DataFrame | None = None) -> Path:
    cfg = load_model()["macro"]
    source = source or get_source()
    fred = fred or get_fred()
    need = MACRO_TICKERS + MARKET_TICKERS
    if prices is None or not set(need) <= set(prices.columns):
        prices = source.prices(need, start="2012-01-01")
    series = fred.frame(list(SERIES), start="2012-01-01")
    for k, s in series.items():
        store.save_prices(f"{fred.name}_{k}", s.to_frame(k))
    df = compute(prices[MACRO_TICKERS].dropna(), series, cfg.get("neutral"))
    payload = build(df, f"{source.name}+{fred.name}", cfg["regime_expansion_min"], cfg["regime_riskoff_max"], prices)
    MACRO_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(MACRO_PATH, payload, separators=(",", ":"))
    return MACRO_PATH
