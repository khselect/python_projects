"""⓪ 시장 개요 (market_monitor 패널 4개)와 국면 점수 검증 (v0.21)."""

import numpy as np
import pandas as pd

from pf.config import load_overview
from pf.data.fred import SyntheticFred
from pf.data.sources import SyntheticSource
from pf.macro.evaluate import episodes, evaluate
from pf.publish.overview import build, price_stats, vix_regime, yield_stats


def test_price_stats_periods_and_52w():
    idx = pd.bdate_range("2025-01-01", periods=300)
    s = pd.Series(np.linspace(100, 130, 300), index=idx)
    st = price_stats(s)
    assert st["last"] == 130 and st["pos52"] == 1.0 and st["from_hi"] == 0.0
    assert abs(st["1D"] - (130 / s.iloc[-2] - 1)) < 1e-5 and st["vs_ma200"] > 0 and len(st["spark"]) == 60
    assert price_stats(pd.Series(dtype=float)) == {"missing": True}


def test_yield_changes_in_bp():
    idx = pd.bdate_range("2025-11-01", periods=40)
    y = yield_stats(pd.Series(np.r_[np.full(39, 4.0), 4.25], index=idx))
    assert y["bp"]["1D"] == 25.0 and y["last"] == 4.25


def test_vix_regime_thresholds():
    s = lambda v: pd.Series([v] * 6, index=pd.bdate_range("2026-11-01", periods=6))  # noqa: E731
    assert vix_regime(s(15))["label"] == "안정" and vix_regime(s(20))["label"] == "보통" and vix_regime(s(40))["label"] == "위기"


def test_build_overview_offline():
    cfg = load_overview()
    syms = [i["symbol"] for k in ("indices", "commodities", "sectors") for i in cfg["panels"][k]["items"]]
    px = SyntheticSource().prices(syms, start="2024-06-01")
    ys = SyntheticFred().frame([i["symbol"] for i in cfg["panels"]["treasuries"]["items"]], start="2024-06-01")
    d = build(px, ys, cfg, "synthetic")
    assert [len(d["panels"][k]["items"]) for k in ("indices", "commodities", "treasuries", "sectors")] == [8, 6, 5, 11]
    assert d["vix_regime"]["label"] in ("안정", "보통", "위기")
    c = d["panels"]["treasuries"]["curve"]
    assert c["maturities"] == [1, 2, 5, 10, 30] and len(c["현재"]) == 5
    assert d["panels"]["treasuries"]["spread"]["bp"] is not None


def test_synthetic_prices_same_regardless_of_start():
    """⓪(2년)과 ①(2007~)이 같은 종목에서 같은 값을 보이도록 합성 경로는 시작일과 무관해야 한다."""
    a = SyntheticSource().prices(["^VIX", "^GSPC"], start="2024-01-01")
    b = SyntheticSource().prices(["^VIX", "^GSPC"], start="2012-01-01")
    assert np.allclose(a.iloc[-5:].to_numpy(), b.iloc[-5:].to_numpy())


def test_episodes_and_detection_lag():
    idx = pd.bdate_range("2020-01-01", periods=400)
    v = np.r_[np.linspace(100, 120, 100), np.linspace(120, 90, 60), np.linspace(90, 130, 240)]
    px = pd.Series(v, index=idx)
    eps = episodes(px)
    assert len(eps) == 1 and eps[0]["peak"] == idx[100]  # 같은 값이면 나중 날을 고점으로 and abs(eps[0]["depth"] + 0.25) < 1e-9
    df = pd.DataFrame(index=idx)
    df["score_macro"] = 0.0
    df["score"] = 0.0
    df["stress"] = 0.0
    for c in ("raw_vix", "raw_trend", "raw_sectors", "raw_rates"):
        df[c] = 0.0
    df.loc[idx[125]:idx[160], "score"] = -5  # 고점 후 25거래일에 위험회피
    df["score_market"] = 0.0
    res = evaluate(df, px, 4, -4)
    v10, v6 = res["variants"]["v10"], res["variants"]["v6"]
    assert v10["detected"] == 1 and v10["per_episode"][0]["lag_from_peak"] == 25
    assert v6["missed"] == 1  # 매크로 층만 보는 기존안은 놓침
