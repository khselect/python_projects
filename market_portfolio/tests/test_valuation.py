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


def _split_case(restated: bool):
    """NVDA형: 2021-07 4:1, 2024-06 10:1. restated=True면 보고 주식수가 이미 현재 기준(AV가 나중 보고서 값으로 수정)."""
    ends = pd.date_range("2020-03-31", "2025-03-31", freq="QE")
    cur = 24.4e9  # 현재 기준 주식수
    sp = pd.Series([4.0, 10.0], index=pd.to_datetime(["2021-07-20", "2024-06-10"]))
    if restated:
        shares = np.full(len(ends), cur)
    else:
        f = np.where(ends < "2021-07-20", 40.0, np.where(ends < "2024-06-10", 10.0, 1.0))
        shares = cur / f
    return ends, sp, shares


def test_split_factor_as_filed_shares_are_adjusted():
    from pf.valuation import split_factor

    ends, sp, shares = _split_case(restated=False)
    adj = shares * split_factor(ends, sp, shares)
    assert np.allclose(adj, 24.4e9)


def test_split_factor_restated_shares_not_double_counted():
    """11-28 운영: AV 주식수가 이미 분할 반영 → 항상 곱하면 시가총액 40배·10배, 그룹 P/E 1,000배."""
    from pf.valuation import split_factor

    ends, sp, shares = _split_case(restated=True)
    assert np.allclose(split_factor(ends, sp, shares), 1.0)


def test_split_factor_mixed_and_trailing_split():
    from pf.valuation import split_factor

    ends, sp, shares = _split_case(restated=False)
    shares = shares.copy()
    shares[ends < "2021-07-20"] *= 4  # 2021 분할은 이미 반영, 2024 분할은 제출 당시 값
    adj = shares * split_factor(ends, sp, shares)
    assert np.allclose(adj, 24.4e9)
    late = pd.Series([2.0], index=pd.to_datetime(["2025-06-01"]))  # 마지막 분기 뒤 분할 → 분할 전 값으로 보고 곱함
    assert np.allclose(split_factor(ends, late, np.full(len(ends), 1e9)), 2.0)


def test_insight_decomposes_pe_change():
    from pf.valuation import insight

    idx = pd.bdate_range("2023-01-02", periods=400)
    mcap = pd.Series(np.linspace(1000, 1200, 400), index=idx)
    ni = pd.Series(np.r_[np.full(148, 20.0), np.full(252, 40.0)], index=idx)
    df = pd.DataFrame({"mcap": mcap, "ni": ni, "fcf": ni * 0.8, "ocf": ni * 1.2, "capex": ni * 0.4, "n": 3})
    df["pe"], df["conv"], df["capex_share"] = df["mcap"] / df["ni"], df["fcf"] / df["ni"], df["capex"] / df["ocf"]
    ins = insight(df)
    assert abs(ins["ni_chg_1y"] - 1.0) < 1e-9 and ins["mcap_chg_1y"] > 0  # 이익 두 배 → 배수 하락은 이익 쪽
    assert ins["pe"] < ins["pe_1y"] and 0 <= ins["pe_pct"] <= 1
    df.loc[idx[-1], "n"] = 4  # 구성 변화가 있으면 분해 생략
    assert "mcap_chg_1y" not in insight(df)


def test_expanding_percentile_has_no_lookahead():
    from pf.valuation import expanding_pct

    x = pd.Series([1.0, 2, 3, 4, 5, 0.5], index=pd.bdate_range("2024-01-01", periods=6))
    p = expanding_pct(x, min_hist=3)
    assert np.isnan(p.iloc[2]) and p.iloc[3] == 1.0 and p.iloc[5] == 0.0  # 그날까지 이력 기준


def test_history_like_baseline_relative_and_independent_blocks():
    from pf.valuation import history_like

    idx = pd.bdate_range("2016-01-01", periods=1500)
    rng = np.random.default_rng(0)
    metric = pd.Series(30 + np.cumsum(rng.normal(0, 0.3, 1500)), index=idx)
    price = pd.Series(np.exp(np.cumsum(rng.normal(0.0004, 0.01, 1500))), index=idx)
    h = history_like(metric, price)
    x = h["horizons"]["12개월"]
    span = (pd.Timestamp(x["last"]) - pd.Timestamp(x["first"])).days * 252 / 365 + 1
    assert x is not None and 1 <= x["n_indep"] <= min(x["n_days"], span / 252 + 1)  # 겹치는 날짜는 독립 표본이 아님
    assert x["badge"] in ("과거 강세 우위", "과거 약세 우위", "뚜렷한 차이 없음")
    assert x["reference_only"] == (x["n_indep"] < 20)
    assert 0 <= h["now_pct"] <= 1 and "baseline" in x
