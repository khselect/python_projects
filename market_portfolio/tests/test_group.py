import json

import numpy as np
import pandas as pd

from pf.events.reactions import event_paths
from pf.publish.group import monthly_heatmap


def test_event_paths_align_reaction_day():
    days = pd.bdate_range("2024-01-01", periods=400)
    bench = pd.Series(100.0, index=days)
    px = pd.Series(100.0, index=days)
    j = 300
    px.iloc[j:] *= 1.10  # 반응일 +10%
    earn = pd.DataFrame({"date": [days[j - 1]], "timing": ["AMC"], "eps_est": [1.0], "eps_act": [1.1], "surprise_pct": [10.0]})
    p = event_paths(px, bench, earn, pre=5, post=20)
    assert list(p.columns) == list(range(-5, 21))
    assert p.index[0] == days[j]
    assert abs(p.loc[days[j], -1]) < 1e-12  # 반응일 전까지 초과수익 0
    assert abs(p.loc[days[j], 0] - 0.10) < 1e-9  # 반응일에 +10%
    assert abs(p.loc[days[j], 20] - 0.10) < 1e-9


def test_event_paths_skips_incomplete_window():
    days = pd.bdate_range("2024-01-01", periods=300)
    s = pd.Series(np.linspace(100, 120, 300), index=days)
    earn = pd.DataFrame({"date": [days[290]], "timing": ["AMC"], "eps_est": [1.0], "eps_act": [1.0], "surprise_pct": [0.0]})
    assert event_paths(s, s, earn, pre=5, post=63).empty


def test_monthly_heatmap_equal_weight_and_annual():
    days = pd.bdate_range("2025-01-01", "2025-12-31")
    # A는 매달 +2%, B는 매달 0% → 그룹 월수익 1%, 벤치마크 0%
    month_idx = np.array([d.month for d in days])
    a = pd.Series(100 * 1.02 ** (month_idx - 1), index=days)
    b = pd.Series(100.0, index=days)
    px = pd.DataFrame({"A": a, "B": b, "BM": b})
    h = monthly_heatmap(px, ["A", "B"], "BM")
    assert h["years"] == [2025]
    row = h["values"][0]
    assert row[0] is None  # 첫 달은 전월 말이 없어 계산 불가
    assert all(abs(v - 0.01) < 1e-9 for v in row[1:])
    assert abs(h["annual"][0] - (1.01**11 - 1)) < 1e-5  # JSON은 소수 5자리 반올림
    assert h["bench_annual"][0] == 0.0


def test_heatmap_month_mdd_catches_intramonth_drop():
    # 10월 말 100 → 11월 중순 78(−22%) → 11월 말 95: 월수익 −5%인데 월중 최대 낙폭 −22%
    days = pd.bdate_range("2026-10-01", "2026-11-30")
    a = pd.Series(100.0, index=days)
    nov = days[days.month == 11]
    a.loc[nov] = np.interp(np.arange(len(nov)), [0, len(nov) // 2, len(nov) - 1], [100, 78, 95])
    px = pd.DataFrame({"A": a, "BM": pd.Series(100.0, index=days) * np.linspace(1, 1.02, len(days))})
    h = monthly_heatmap(px, ["A"], "BM")
    i = h["years"].index(2026)
    assert abs(h["values"][i][10] - (-0.05)) < 1e-4
    assert abs(h["mdd"][i][10] - (-0.22)) < 1e-4
    assert h["bench_values"][i][10] > 0
