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


def build(df: pd.DataFrame, source_name: str, hi: int = 3, lo: int = -3) -> dict:
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
        "indicators": indicators,
        "compare": {str(m): _snapshot(df, asof - pd.DateOffset(months=m), hi, lo) for m in COMPARE_MONTHS},
        "history": {"dates": [d.date().isoformat() for d in weekly.index], "score": [int(v) for v in weekly]},
        "notice": {"fred": NOTICE, "terms_url": TERMS_URL, "internal_only": sorted(INTERNAL_ONLY)},
    }


def publish_macro(source: Source | None = None, fred=None, prices: pd.DataFrame | None = None) -> Path:
    cfg = load_model()["macro"]
    source = source or get_source()
    fred = fred or get_fred()
    if prices is None or not set(MACRO_TICKERS) <= set(prices.columns):
        prices = source.prices(MACRO_TICKERS, start="2012-01-01")
    series = fred.frame(list(SERIES), start="2012-01-01")
    for k, s in series.items():
        store.save_prices(f"{fred.name}_{k}", s.to_frame(k))
    df = compute(prices[MACRO_TICKERS].dropna(), series)
    payload = build(df, f"{source.name}+{fred.name}", cfg["regime_expansion_min"], cfg["regime_riskoff_max"])
    MACRO_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(MACRO_PATH, payload, separators=(",", ":"))
    return MACRO_PATH
