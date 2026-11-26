import json

import numpy as np
import pandas as pd
import pytest

import pf.data.fundamentals as F
import pf.publish.valuation as PV
import pf.valuation as V
from pf.data.sources import SyntheticSource


def q(ni, ocf, capex, shares, start="2024-03-31"):
    idx = pd.date_range(start, periods=len(ni), freq="QE")
    return pd.DataFrame({"net_income": ni, "ocf": ocf, "capex": capex, "shares": shares}, index=idx)


def test_ttm_needs_four_quarters_and_lags_release():
    t = V.ttm(q([1, 1, 1, 1, 2], [2] * 5, [1] * 5, [10] * 5), lag_days=45)
    assert len(t) == 2  # 4번째 분기부터
    assert t.index[0] == pd.Timestamp("2024-12-31") + pd.Timedelta(days=45)
    assert t["ni_ttm"].tolist() == [4, 5] and t["fcf_ttm"].tolist() == [4, 4]


def test_split_adjusts_shares_reported_before_split():
    ends = pd.DatetimeIndex(["2024-03-31", "2024-09-30"])
    f = V.split_factor(ends, pd.Series([10.0], index=[pd.Timestamp("2024-06-10")]))
    assert f.tolist() == [10.0, 1.0]  # 분할 전 분기 주식수 × 10


def test_ticker_daily_market_cap_consistent_across_split():
    # 분할 전 주식 100주·주가 1000 → 분할(10:1) 후 1000주·주가 100. 분할 반영 종가 기준이면 둘 다 100.
    qq = q([10] * 6, [20] * 6, [5] * 6, [100, 100, 100, 1000, 1000, 1000], start="2023-03-31")
    days = pd.bdate_range("2024-03-01", "2024-12-31")
    close = pd.Series(100.0, index=days)  # Yahoo 종가는 분할 반영
    d = V.ticker_daily(close, qq, pd.Series([10.0], index=[pd.Timestamp("2023-11-15")]), lag_days=45)
    assert d["mcap"].dropna().round(6).nunique() == 1 and d["mcap"].dropna().iloc[0] == pytest.approx(100_000)


def test_group_series_aggregates_and_blanks_nonpositive():
    idx = pd.bdate_range("2025-01-01", periods=3)
    a = pd.DataFrame({"mcap": 100.0, "ni": 5.0, "fcf": 4.0, "ocf": 6.0, "capex": 2.0}, index=idx)
    b = pd.DataFrame({"mcap": 300.0, "ni": 15.0, "fcf": -20.0, "ocf": 1.0, "capex": 21.0}, index=idx)
    g = V.group_series({"A": a, "B": b})
    assert g["pe"].iloc[0] == pytest.approx(400 / 20)
    assert np.isnan(g["pfcf"].iloc[0])  # 그룹 FCF 합이 음수면 비움
    assert g["n"].iloc[0] == 2


def test_group_forward_pe_is_harmonic_by_market_cap():
    f = pd.DataFrame({"date": pd.Timestamp("2026-11-26"), "ticker": ["A", "B", "C"],
                      "market_cap": [100.0, 300.0, 50.0], "forward_pe": [20.0, 30.0, -5.0]})
    s = V.group_forward_pe(f, ["A", "B", "C"])
    assert s.iloc[0] == pytest.approx(400 / (5 + 10))  # 음수 선행 P/E 종목은 제외


@pytest.fixture
def tmp_val(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "DATA_DIR", tmp_path)
    monkeypatch.setattr(V, "DATA_DIR", tmp_path)
    monkeypatch.setattr(PV, "VAL_DIR", tmp_path / "publish" / "valuation")
    return tmp_path


class Counting(F.SyntheticFundamentals):
    def __init__(self, limit=None):
        super().__init__(); self.calls = 0; self.limit = limit

    def quarterly(self, s):
        if self.limit is not None and self.calls + 2 > self.limit:
            raise F.RateLimited("한도")
        self.calls += 2
        return super().quarterly(s)


def test_refresh_respects_daily_budget_and_priority(tmp_val):
    syms = PV.priority_symbols()
    assert syms[:7] == ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX", "TSLA"]  # 빅테크 먼저
    r1 = F.refresh(syms, Counting(), call_budget=20)
    assert len(r1["fetched"]) == 10 and r1["fetched"][0] == "AAPL"
    r2 = F.refresh(syms, Counting(), call_budget=20)
    assert not set(r1["fetched"]) & set(r2["fetched"])  # 다음 날은 이어서
    r3 = F.refresh(syms, Counting(limit=4), call_budget=20)
    assert len(r3["fetched"]) == 2 and r3["stopped"]  # 한도 걸리면 멈춤


def test_publish_valuation_offline(tmp_val):
    out = PV.publish_valuation(SyntheticSource(), Counting(), refresh=True)
    assert out["groups"] >= 1
    d = json.loads((tmp_val / "publish" / "valuation" / "bigtech.json").read_text(encoding="utf-8"))
    assert len(d["coverage"]["have"]) == 7 and not d["coverage"]["missing"]
    pe, pf_, conv = d["ttm"]["pe"], d["ttm"]["pfcf"], d["ttm"]["conv"]
    assert len(pe) > 200 and all(v is None or v > 0 for v in pe)
    # 합성 데이터는 최근 설비투자 급증 → FCF 전환율 하락, 괴리 확대
    assert conv[-1] < conv[-60] and d["ttm"]["gap"][-1] > d["ttm"]["gap"][-60]
    assert len(d["forward_pe"]["values"]) == 1  # 오늘부터 누적
    assert (tmp_val / "publish" / "valuation" / "bigtech.json").stat().st_size < 50 * 1024
