"""I. 시장 개요 (market_monitor 패널 4개)와 국면 점수 검증 (v0.21)."""

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
    """I(2년)과 II(2007~)이 같은 종목에서 같은 값을 보이도록 합성 경로는 시작일과 무관해야 한다."""
    a = SyntheticSource().prices(["^VIX", "^GSPC"], start="2024-01-01")
    b = SyntheticSource().prices(["^VIX", "^GSPC"], start="2012-01-01")
    assert np.allclose(a.iloc[-5:].to_numpy(), b.iloc[-5:].to_numpy())


def test_episodes_and_detection_lag():
    idx = pd.bdate_range("2020-01-01", periods=400)
    v = np.r_[np.linspace(100, 120, 100), np.linspace(120, 90, 60), np.linspace(90, 130, 240)]
    px = pd.Series(v, index=idx)
    eps = episodes(px)
    assert len(eps) == 1 and eps[0]["peak"] == idx[99]  # 52주 안 최고가 처음 나온 날 and abs(eps[0]["depth"] + 0.25) < 1e-9
    df = pd.DataFrame(index=idx)
    df["score_macro"] = 0.0
    df["score"] = 0.0
    df["stress"] = 0.0
    for c in ("raw_vix", "raw_trend", "raw_sectors", "raw_rates"):
        df[c] = 0.0
    df.loc[idx[125]:idx[160], "score"] = -5  # 고점 후 26거래일에 위험회피
    df["score_market"] = 0.0
    res = evaluate(df, px, 4, -4)
    v10, v6 = res["variants"]["v10"], res["variants"]["v6"]
    assert v10["detected"] == 1 and v10["per_episode"][0]["lag_from_peak"] == 26
    assert v6["missed"] == 1  # 매크로 층만 보는 기존안은 놓침


def test_episodes_use_52_week_high_not_all_time_high():
    """v0.22: 역대 최고가 기준이면 큰 하락 뒤 회복 전의 두 번째 하락(2010·2011형)이 한 구간에 묻힌다."""
    idx = pd.bdate_range("2008-01-01", periods=1200)
    v = np.r_[np.linspace(100, 60, 300),      # 큰 하락 (−40%)
              np.linspace(60, 85, 400),       # 회복하지만 이전 고점(100) 아래
              np.linspace(85, 68, 100),       # 두 번째 하락 −20% (52주 고점 85 기준)
              np.linspace(68, 110, 400)]
    eps = episodes(pd.Series(v, index=idx))
    assert len(eps) == 2
    assert abs(eps[1]["depth"] + 0.20) < 0.01 and eps[1]["peak"] == idx[699]


def test_stress_hysteresis_enter_fast_exit_slow():
    from pf.macro.indicators import stress_hold

    idx = pd.RangeIndex(12)
    entry = pd.Series([0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], index=idx).astype(bool)
    calm = pd.Series([1, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1], index=idx).astype(bool)
    on, run = stress_hold(entry, calm, 5)
    assert on.tolist() == [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0]  # 진정이 끊기면(5번째 날) 다시 셈, 5일 연속 뒤 해제
    assert run.iloc[9] == 4 and run.iloc[10] == 0


def test_eval_reports_immediate_vs_hysteresis():
    idx = pd.bdate_range("2020-01-01", periods=400)
    px = pd.Series(np.r_[np.linspace(100, 120, 100), np.linspace(120, 90, 60), np.linspace(90, 130, 240)], index=idx)
    df = pd.DataFrame(0.0, index=idx, columns=["score_macro", "score", "score_market", "stress", "stress_entry",
                                               "raw_vix", "raw_trend", "raw_sectors", "raw_rates"])
    df.loc[idx[130]:idx[131], "stress_entry"] = 1   # 이틀만 진입 조건
    df.loc[idx[130]:idx[150], "stress"] = 1         # 히스테리시스로 더 길게 유지
    res = evaluate(df, px, 4, -4)
    vi, v10 = res["variants"]["v10i"], res["variants"]["v10"]
    assert vi["detected"] == v10["detected"] == 1
    assert v10["riskoff_share"] > vi["riskoff_share"]


def test_overlapping_episodes_merge():
    """52주 창이 밀리며 같은 약세장이 두 구간으로 갈리던 문제 (2022-01·2022-03 고점, v0.22)."""
    idx = pd.bdate_range("2021-01-01", periods=700)
    v = np.r_[np.linspace(100, 120, 250), np.linspace(120, 100, 40), np.linspace(100, 118, 30),  # 고점 120, 소폭 하락 뒤 118
              np.linspace(118, 90, 150),   # 약세장 (−25%)
              np.linspace(90, 107, 80),    # 반등 (52주 고점이 118로 바뀜 → −10% 위로)
              np.linspace(107, 98, 60),    # 재하락 (118 대비 −17%)
              np.linspace(98, 130, 90)]
    eps = episodes(pd.Series(v, index=idx))
    assert len(eps) == 1 and abs(eps[0]["depth"] + 0.25) < 0.01


def test_false_riskoff_share():
    idx = pd.bdate_range("2020-01-01", periods=400)
    px = pd.Series(np.r_[np.linspace(100, 120, 100), np.linspace(120, 90, 60), np.linspace(90, 130, 240)], index=idx)
    df = pd.DataFrame(0.0, index=idx, columns=["score_macro", "score", "score_market", "stress", "stress_entry",
                                               "raw_vix", "raw_trend", "raw_sectors", "raw_rates"])
    df.loc[idx[120]:idx[159], "score"] = -5   # 하락 구간 안 40일
    df.loc[idx[300]:idx[339], "score"] = -5   # 구간 밖 40일 (헛 위험회피)
    v = evaluate(df, px, 4, -4)["variants"]["v10"]
    assert v["false_riskoff_share"] == round(40 / 400, 3) and v["riskoff_in_episodes"] > 0.4
