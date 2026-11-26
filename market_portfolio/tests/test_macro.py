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
    assert regime_of(3) == "확장" and regime_of(2) == "중립·전환" and regime_of(-3) == "위험회피"


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
    assert set(df[[f"sig_{i.key}" for i in INDICATORS]].stack().unique()) <= {-1.0, 1.0}
    # 신용 신호는 최근 3년 이전에는 없다
    assert df["sig_credit"].loc[:"2022-01-01"].isna().all()
    assert df["sig_credit"].iloc[-1] in (-1.0, 1.0)
    assert df["n_signals"].iloc[-1] == 6


def test_publish_macro_offline(tmp_path, monkeypatch, macro_df):
    monkeypatch.setattr(mpub, "MACRO_PATH", tmp_path / "macro.json")
    import pf.data.store as store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    p = mpub.publish_macro(source=SyntheticSource(), fred=SyntheticFred())
    import json

    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["regime"] in ("확장", "중립·전환", "위험회피")
    assert len(d["indicators"]) == 6 and set(d["compare"]) == {"3", "6", "12"}
    credit = next(i for i in d["indicators"] if i["key"] == "credit")
    assert credit["public_values"] is False and set(credit["values"]) == {"direction"}  # 값 비공개
    assert 90 <= len(d["history"]["score"]) <= 110  # 2년 주간
    assert "FRED" in d["notice"]["fred"]
    assert p.stat().st_size < 50 * 1024
