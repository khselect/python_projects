"""I. 시장 개요 → data/publish/overview.json (화면이 읽는 유일한 파일).

market_monitor(khselect/market_monitor)의 화면 패널 4개(주요 지수·원자재·미 국채·섹터)를 옮긴 것.
화면 구성은 config/overview.yaml. 수치 계산만 하고 판정은 하지 않는다 — 판정은 II. 국면 점수(시장 층)가 맡는다.
예외: VIX 국면 배지(안정·보통·위기)는 market_monitor와 같은 경계로 여기서 붙인다.

S0(비공개) 전용 — 지수·선물 시세가 Yahoo 파생. 공개(S1) 전 라이선스 데이터로 교체.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pf.config import load_overview
from pf.data.fred import NOTICE, TERMS_URL, get_fred
from pf.data.sources import Source, get_source
from pf.publish.ticker import PUBLISH_DIR, _write_json

OVERVIEW_PATH = PUBLISH_DIR.parent / "overview.json"
SPARK_DAYS = 60
PERIODS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "1Y": 252}
CURVE_AGO = {"현재": 0, "1개월 전": 21, "1년 전": 252}


def _f(v, nd: int = 5):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def _chg(s: pd.Series, n: int):
    return _f(s.iloc[-1] / s.iloc[-1 - n] - 1) if len(s) > n else None


def _ytd(s: pd.Series):
    prev = s[s.index.year < s.index[-1].year]
    return _f(s.iloc[-1] / prev.iloc[-1] - 1) if len(prev) else None


def price_stats(s: pd.Series) -> dict:
    """가격 시리즈 요약. 각 시리즈의 마지막 유효일 기준 (한국·미국 휴장일이 다름)."""
    s = s.dropna()
    if len(s) < 2:
        return {"missing": True}
    y1 = s[s.index > s.index[-1] - pd.DateOffset(years=1)]
    ma = s.rolling(200).mean().iloc[-1] if len(s) >= 200 else np.nan
    vol = np.log(s).diff().tail(20).std() * np.sqrt(252)
    hi, lo = y1.max(), y1.min()
    return {
        "date": s.index[-1].date().isoformat(),
        "last": _f(s.iloc[-1], 4),
        **{k: _chg(s, n) for k, n in PERIODS.items()},
        "YTD": _ytd(s),
        "hi52": _f(hi, 4), "lo52": _f(lo, 4),
        "pos52": _f((s.iloc[-1] - lo) / (hi - lo)) if hi > lo else None,
        "from_hi": _f(s.iloc[-1] / hi - 1),
        "vs_ma200": _f(s.iloc[-1] / ma - 1) if np.isfinite(ma) else None,
        "vol20": _f(vol),
        "spark": [_f(v, 4) for v in s.tail(SPARK_DAYS)],
    }


def yield_stats(s: pd.Series) -> dict:
    """금리 시리즈 (%) — 변화는 bp."""
    s = s.dropna()
    if len(s) < 2:
        return {"missing": True}
    bp = lambda n: _f((s.iloc[-1] - s.iloc[-1 - n]) * 100, 1) if len(s) > n else None  # noqa: E731
    prev = s[s.index.year < s.index[-1].year]
    return {
        "date": s.index[-1].date().isoformat(),
        "last": _f(s.iloc[-1], 3),
        "bp": {"1D": bp(1), "1W": bp(5), "1M": bp(21), "YTD": _f((s.iloc[-1] - prev.iloc[-1]) * 100, 1) if len(prev) else None},
        "spark": [_f(v, 3) for v in s.tail(SPARK_DAYS)],
    }


def vix_regime(vix: pd.Series, thresholds=(17, 25), window: int = 5) -> dict | None:
    v = vix.dropna()
    if len(v) < window:
        return None
    avg = float(v.tail(window).mean())
    lo, hi = thresholds
    label = "안정" if avg < lo else ("보통" if avg < hi else "위기")
    return {"label": label, "avg": _f(avg, 2), "last": _f(v.iloc[-1], 2), "max_1m": _f(v.tail(21).max(), 2),
            "window": window, "thresholds": list(thresholds)}


def build(prices: pd.DataFrame, yields: dict[str, pd.Series], cfg: dict, source_name: str) -> dict:
    panels = cfg["panels"]
    out_panels = {}
    for key in ("indices", "commodities", "sectors"):
        items = []
        for it in panels[key]["items"]:
            col = prices[it["symbol"]] if it["symbol"] in prices else pd.Series(dtype=float)
            items.append({"id": it["id"], "name": it["name"], "symbol": it["symbol"], **price_stats(col)})
        out_panels[key] = {"title": panels[key]["title"], "items": items}

    t_items, curves = [], {k: [] for k in CURVE_AGO}
    for it in panels["treasuries"]["items"]:
        s = yields.get(it["symbol"], pd.Series(dtype=float)).dropna()
        t_items.append({"id": it["id"], "name": it["name"], "maturity": it["maturity"], **yield_stats(s)})
        for k, n in CURVE_AGO.items():
            curves[k].append(_f(s.iloc[-1 - n], 3) if len(s) > n else None)
    by = {i["id"]: i.get("last") for i in t_items}
    spread = None
    if by.get("UST10Y") is not None and by.get("UST2Y") is not None:
        s10, s2 = yields["DGS10"].dropna(), yields["DGS2"].dropna()
        sp = (s10 - s2).dropna()
        spread = {"label": "10년 − 2년", "bp": _f(sp.iloc[-1] * 100, 1),
                  "bp_1m": _f((sp.iloc[-1] - sp.iloc[-22]) * 100, 1) if len(sp) > 22 else None,
                  "inverted": bool(sp.iloc[-1] < 0)}
    out_panels["treasuries"] = {
        "title": panels["treasuries"]["title"], "items": t_items,
        "curve": {"maturities": [i["maturity"] for i in t_items], **curves}, "spread": spread,
    }

    vr = cfg.get("vix_regime", {})
    vix_sym = next((i["symbol"] for i in panels["indices"]["items"] if i["id"] == "VIX"), "^VIX")
    vix = vix_regime(prices[vix_sym], tuple(vr.get("thresholds", (17, 25))), vr.get("window", 5)) if vix_sym in prices else None
    asof = max((i["date"] for p in out_panels.values() for i in p["items"] if i.get("date")), default=None)
    return {
        "schema": 1,
        "asof": asof,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source_name,
        "panels": out_panels,
        "vix_regime": vix,
        "notice": {"fred": NOTICE, "terms_url": TERMS_URL},
    }


def publish_overview(source: Source | None = None, fred=None) -> Path:
    cfg = load_overview()
    source = source or get_source()
    fred = fred or get_fred()
    start = (pd.Timestamp.today().normalize() - pd.DateOffset(years=2, months=3)).date().isoformat()
    syms = [i["symbol"] for k in ("indices", "commodities", "sectors") for i in cfg["panels"][k]["items"]]
    prices = source.prices(syms, start=start)
    ys = [i["symbol"] for i in cfg["panels"]["treasuries"]["items"]]
    yields = fred.frame(ys, start=start)
    payload = build(prices, yields, cfg, f"{source.name}+{fred.name}")
    OVERVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(OVERVIEW_PATH, payload, separators=(",", ":"))
    return OVERVIEW_PATH


def load_overview_json() -> dict | None:
    return json.loads(OVERVIEW_PATH.read_text(encoding="utf-8")) if OVERVIEW_PATH.exists() else None
