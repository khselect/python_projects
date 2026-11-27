import numpy as np
import pandas as pd
import pytest

import pf.macro.publish as mpub
from pf.data.fred import SyntheticFred
from pf.data.sources import SyntheticSource
from pf.macro.indicators import (
    INDICATORS,
    compute,
    confirm,
    days_since_inversion,
    gdp_yoy_available,
    last_switch,
    regime_of,
)


def test_confirm_needs_five_consecutive_days():
    raw = pd.Series([1, 1, 1, 1, 1, -1, -1, -1, -1, 1, -1, -1, -1, -1, -1], dtype=float)
    c = confirm(raw).tolist()
    assert np.isnan(c[3]) and c[4] == 1  # 처음 5일째 확정
    assert c[8] == 1  # −1 네 번 뒤 +1로 끊겨 전환 없음
    assert c[13] == 1 and c[14] == -1  # −1 5일 연속 → 전환


def test_regime_thresholds():
    assert regime_of(4) == "확장" and regime_of(3) == "중립·전환" and regime_of(-4) == "위험회피"
    assert regime_of(3, hi=3, lo=-3) == "확장"  # 경계는 설정값
    assert regime_of(5, stress=True) == "위험회피(급변)"  # 급변 규칙은 점수보다 우선


def test_gdp_released_with_lag_no_lookahead():
    q = pd.date_range("2024-01-01", periods=8, freq="QS")
    gdp = pd.Series(np.linspace(100, 108, 8), index=q)
    yoy = gdp_yoy_available(gdp)
    # 2025Q1(1월 1일 시작) 값은 3월 말 + 30일 = 4월 30일에야 쓸 수 있다
    assert yoy.index[0] == pd.Timestamp("2025-04-30")


def test_curve_needs_182_days_after_uninversion():
    idx = pd.date_range("2025-01-01", periods=400, freq="D")
    curve = pd.Series(np.where(np.arange(400) < 100, -0.5, 0.5), index=idx)
    d = days_since_inversion(curve)
    assert d.iloc[99] == 0 and d.iloc[100 + 181] == 182


def test_last_switch_ignores_first_appearance():
    s = pd.Series([np.nan, 1, 1, -1, -1], index=pd.date_range("2026-01-01", periods=5))
    assert last_switch(s) == "2026-01-04"
    assert last_switch(pd.Series([1.0, 1.0], index=pd.date_range("2026-01-01", periods=2))) is None


@pytest.fixture
def macro_df():
    px = SyntheticSource().prices(mpub.MACRO_TICKERS)
    return compute(px, SyntheticFred().frame(["DFEDTARU", "GDP", "BAMLH0A0HYM2", "T10Y2Y", "DTWEXBGS"]))


def test_compute_scores_in_range_and_credit_only_recent(macro_df):
    df = macro_df
    assert df["score"].between(-6, 6).all()
    assert set(df[[f"sig_{i.key}" for i in INDICATORS]].stack().unique()) <= {-1.0, 0.0, 1.0}
    assert (df["score"] % 2 == 1).any()  # 중립 구간이 있어 홀수 점수도 나온다 (결정 B)
    # 신용 신호는 최근 3년 이전에는 없다
    assert df["sig_credit"].loc[:"2022-01-01"].isna().all()
    assert df["sig_credit"].iloc[-1] in (-1.0, 0.0, 1.0)
    assert df["n_signals"].iloc[-1] == 6


def test_publish_macro_offline(tmp_path, monkeypatch, macro_df):
    monkeypatch.setattr(mpub, "MACRO_PATH", tmp_path / "macro.json")
    import pf.data.store as store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    p = mpub.publish_macro(source=SyntheticSource(), fred=SyntheticFred())
    import json

    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["regime"] in ("확장", "중립·전환", "위험회피", "위험회피(급변)")
    assert len(d["indicators"]) == 10 and set(d["compare"]) == {"3", "6", "12"}
    assert d["score_range"] == 10 and d["thresholds"] == {"expansion": 4, "riskoff": -4}
    assert d["layers"]["macro"]["n"] == 6 and d["layers"]["market"]["n"] == 4
    assert d["score"] == d["layers"]["macro"]["score"] + d["layers"]["market"]["score"]
    h = d["history"]
    assert [a + b for a, b in zip(h["macro"], h["market"])] == h["score"] and len(h["stress"]) == len(h["score"])
    credit = next(i for i in d["indicators"] if i["key"] == "credit")
    assert credit["public_values"] is False and set(credit["values"]) == {"direction"}  # 값 비공개
    assert 90 <= len(d["history"]["score"]) <= 110  # 2년 주간
    assert "FRED" in d["notice"]["fred"]
    assert p.stat().st_size < 50 * 1024
    m = d["markets"]
    assert set(m["series"]) == {"QQQ", "OEF"} and m["series"]["QQQ"][0] == 100.0 and m["ratio"][0] == 100.0
    assert len(m["dates"]) == len(m["ratio"]) and abs(len(m["dates"]) - len(d["history"]["dates"])) <= 2


def test_neutral_bands_per_indicator():
    from pf.macro.indicators import _tri

    v = pd.Series([0.02, 0.005, -0.005, -0.02])
    sig = _tri(v > 0.01, v < -0.01, v.notna()).tolist()
    assert sig == [1.0, 0.0, 0.0, -1.0]


def _market_frame(n=400, vix=15.0, spx_drop=0.0, ndx_drop=0.0, y2_jump=0.0, sectors_up=True):
    idx = pd.bdate_range("2024-01-01", periods=n)
    up = np.linspace(100, 130, n)
    px = pd.DataFrame({"DBC": up, "RSP": up, "SPY": up}, index=idx)
    px["^VIX"] = vix
    px["^GSPC"] = up * np.r_[np.ones(n - 10), np.full(10, 1 + spx_drop)]
    px["^NDX"] = up * np.r_[np.ones(n - 10), np.full(10, 1 + ndx_drop)]
    for t in ("XLK", "XLC", "XLY", "XLF", "XLV", "XLI", "XLE", "XLB", "XLP", "XLU", "XLRE"):
        px[t] = up if sectors_up else up[::-1]
    y2 = pd.Series(4.0, index=idx)
    y2.iloc[-15:] += y2_jump
    fred = SyntheticFred(end=str(idx[-1].date())).frame(["DFEDTARU", "GDP", "BAMLH0A0HYM2", "T10Y2Y", "DTWEXBGS"], start="2024-01-01")
    fred["DGS2"] = y2
    return px, fred


def test_market_layer_calm_market_is_favorable():
    px, fred = _market_frame()
    last = compute(px, fred).iloc[-1]
    assert last["sig_vix"] == 1 and last["sig_trend"] == 1 and last["sig_sectors"] == 1 and last["sig_rates"] == 1
    assert last["score_market"] == 4 and last["stress"] == 0


def test_market_layer_crash_triggers_stress_and_negatives():
    """나스닥 −25% · VIX 40 · 섹터 하락 · 2년물 급등 → 시장 층 −4, 급변 규칙 발동 (11-26 사례 유형)."""
    px, fred = _market_frame(vix=40.0, spx_drop=-0.15, ndx_drop=-0.25, y2_jump=0.4, sectors_up=False)
    last = compute(px, fred).iloc[-1]
    assert last["score_market"] == -4 and last["stress"] == 1
    assert regime_of(last["score"], stress=last["stress"] == 1) == "위험회피(급변)"


def test_market_layer_confirms_in_two_days():
    px, fred = _market_frame()
    px.iloc[-1, px.columns.get_loc("^VIX")] = 30.0  # 하루만 급등
    df = compute(px, fred)
    assert df["raw_vix"].iloc[-1] == -1 and df["sig_vix"].iloc[-1] == 1  # 하루로는 신호 전환 없음
    assert df["stress"].iloc[-1] == 1  # 급변 규칙은 확정 기간 없이 즉시


def test_missing_market_inputs_leave_signal_empty():
    px, fred = _market_frame()
    df = compute(px[["DBC", "RSP", "SPY"]], {k: v for k, v in fred.items() if k != "DGS2"})
    assert df[["sig_vix", "sig_trend", "sig_sectors", "sig_rates"]].iloc[-1].isna().all()
