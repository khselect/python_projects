import time

import numpy as np

from pf.sim import mixture
from pf.sim.reaction_mc import draw_reaction, simulate


def _sample(m, n, seed=1):
    return draw_reaction(m, n, np.random.default_rng(seed))


TRUE = mixture.Mixture((0.25, 0.45, 0.30), (-0.07, 0.005, 0.06), (0.03, 0.015, 0.03))


def test_mle_recovers_large_sample():
    fit = mixture.fit(_sample(TRUE, 20_000))
    assert np.allclose(fit.means, TRUE.means, atol=0.012)
    assert np.allclose(fit.weights, TRUE.weights, atol=0.08)
    assert list(fit.means) == sorted(fit.means)


def test_map_with_few_events_stays_near_prior():
    x = _sample(TRUE, 8, seed=7)
    fit = mixture.fit(x, prior=TRUE, kappa=5)
    assert fit.method == "map"
    assert np.allclose(fit.weights, TRUE.weights, atol=0.25)
    assert fit.means[0] < 0 < fit.means[2]


def test_simulation_reproducible_and_fast():
    t0 = time.perf_counter()
    a = simulate(TRUE, sigma_daily=0.015, n_iter=400_000, seed=42)
    elapsed = time.perf_counter() - t0
    b = simulate(TRUE, sigma_daily=0.015, n_iter=400_000, seed=42)
    assert a["horizons"]["1"] == b["horizons"]["1"]
    assert a["fan"]["p50"] == b["fan"]["p50"]
    h1 = a["horizons"]["1"]
    assert abs(h1["p_up"] + h1["p_down"] - 1) < 1e-6
    assert h1["pcts"]["5"] < h1["pcts"]["50"] < h1["pcts"]["95"]
    assert h1["cvar5"] < h1["pcts"]["5"]
    # 누적 구간은 시간이 갈수록 넓어진다
    w = {h: a["horizons"][h]["pcts"]["95"] - a["horizons"][h]["pcts"]["5"] for h in ("1", "5", "21", "63")}
    assert w["1"] < w["5"] < w["21"] < w["63"]
    print(f"simulate 400k x 63일: {elapsed:.2f}s")


def test_reaction_draw_400k_under_1s():
    t0 = time.perf_counter()
    _sample(TRUE, 400_000)
    assert time.perf_counter() - t0 < 1.0


def test_no_degenerate_spike_on_overlapping_components():
    # 중립·강세가 겹치는 데이터에서 폭 0에 가까운 성분이 생기지 않아야 한다 (2026-11-26 수정)
    rng = np.random.default_rng(3)
    x = _sample(TRUE, 300, seed=3) + rng.standard_t(5, 300) * 0.012
    fit = mixture.fit(x)
    assert min(fit.scales) >= 0.25 * x.std() - 1e-9
    y = draw_reaction(fit, 200_000, np.random.default_rng(0))
    assert abs(np.mean(y > 0) - np.mean(x > 0)) < 0.05
    assert np.allclose(np.percentile(y, [5, 50, 95]), np.percentile(x, [5, 50, 95]), atol=0.015)
