import numpy as np
import pandas as pd

from pf.data.sources import SyntheticSource
from pf.events.reactions import build_reactions, next_event, reaction_index


def test_reaction_day_amc_is_next_trading_day():
    days = pd.bdate_range("2026-01-05", periods=10)  # 월요일 시작
    fri = pd.Timestamp("2026-01-09")
    assert days[reaction_index(days, fri, "AMC")] == pd.Timestamp("2026-01-12")  # 다음 월요일
    assert days[reaction_index(days, fri, "BMO")] == fri


def test_bmo_on_holiday_rolls_forward():
    days = pd.DatetimeIndex(["2026-01-05", "2026-01-07"])
    assert days[reaction_index(days, pd.Timestamp("2026-01-06"), "BMO")] == pd.Timestamp("2026-01-07")


def test_known_jump_recovered_as_excess_return():
    days = pd.bdate_range("2024-01-01", periods=400)
    bench = pd.Series(100 * np.cumprod(1 + np.r_[0, np.full(399, 0.001)]), index=days)
    px = bench.copy()
    j = 300
    px.iloc[j:] *= 1.10  # 반응일에 +10%
    earn = pd.DataFrame(
        {"date": [days[j - 1]], "timing": ["AMC"], "eps_est": [1.0], "eps_act": [1.1], "surprise_pct": [10.0]}
    )
    r = build_reactions(px, bench, earn)
    assert len(r) == 1
    assert r.loc[0, "reaction_date"] == days[j].date().isoformat()
    assert abs(r.loc[0, "car1"] - 0.10) < 1e-3
    assert abs(r.loc[0, "car63"] - 0.10) < 1e-3  # 이후 동일 수익 → 초과 0


def test_synthetic_pipeline_has_events_and_next_date():
    src = SyntheticSource()
    px = src.prices(["AVGO", "SOXX"])
    earn = src.earnings("AVGO")
    r = build_reactions(px["AVGO"], px["SOXX"], earn)
    assert len(r) >= 40
    nxt = next_event(earn, px.index[-1])
    assert nxt and pd.Timestamp(nxt["date"]) > px.index[-1]
