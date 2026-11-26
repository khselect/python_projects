"""그룹 단위 실적 반응 계산 → 종목별 게시 JSON (data/publish/ticker/{T}.json).

화면(④ 종목 상세)은 이 JSON만 읽는다. 페이지 조회 시 계산·LLM 호출 없음.
"""

from __future__ import annotations

import hashlib
import json
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pf import __version__
from pf.config import load_coverage, load_model
from pf.data import store
from pf.data.sources import Source, get_source
from pf.events.reactions import build_reactions, daily_excess_sigma, next_event
from pf.settings import CONFIG_DIR, DATA_DIR
from pf.sim import mixture
from pf.sim.reaction_mc import simulate

PUBLISH_DIR = DATA_DIR / "publish" / "ticker"
PRED_DIR = DATA_DIR / "predictions"
HISTORY_ROWS = 24


def _config_hash() -> str:
    h = hashlib.sha256()
    for name in ("model.yaml", "coverage.yaml"):
        h.update((CONFIG_DIR / name).read_bytes())
    return h.hexdigest()[:12]


def _seed(base: int, ticker: str) -> int:
    return (base + zlib.crc32(ticker.encode())) % (2**31)


def _clean(v):
    if isinstance(v, float) and not np.isfinite(v):
        return None
    return v


def _history(r: pd.DataFrame) -> list[dict]:
    cols = ["event_date", "timing", "reaction_date", "ret1", "car1", "car5", "car21", "car63", "surprise_pct"]
    tail = r[cols].tail(HISTORY_ROWS).iloc[::-1]
    return [{k: _clean(v) for k, v in row.items()} for row in tail.to_dict("records")]


def fetch(source: Source, tickers: list[str], use_cache: bool = False):
    px = store.load_prices(source.name) if use_cache else None
    if px is None or not set(tickers) <= set(px.columns):
        px = source.prices(tickers)
        store.save_prices(source.name, px)
    earn = {}
    for t in tickers:
        e = store.load_earnings(source.name, t) if use_cache else None
        if e is None:
            e = source.earnings(t)
            store.save_earnings(source.name, t, e)
        earn[t] = e
    return px, earn


def publish_group(group_id: str, source: Source | None = None, use_cache: bool = False) -> list[Path]:
    cov = load_coverage()
    cfg = load_model()
    sim_cfg, mix_cfg, gate = cfg["simulation"], cfg["mixture"], cfg["calibration_gate"]
    g = cov.group(group_id)
    source = source or get_source()

    tickers = list(dict.fromkeys([*g.members, g.benchmark]))
    px, earn = fetch(source, tickers, use_cache)
    bench = px[g.benchmark]
    asof = px.index[-1]

    reactions = {t: build_reactions(px[t], bench, earn[t]) for t in g.members}
    pooled = np.concatenate([r["car1"].dropna().to_numpy() for r in reactions.values() if len(r)])
    prior = None
    if len(pooled) >= mix_cfg["min_group_events"]:
        prior = mixture.fit(pooled, nu=mix_cfg["nu"])

    PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for t in g.members:
        r = reactions[t]
        x = r["car1"].dropna().to_numpy() if len(r) else np.array([])
        if prior is None and len(x) < 3:
            continue
        mix = mixture.fit(x, prior=prior, kappa=mix_cfg["kappa"], nu=mix_cfg["nu"])
        _, sigma = daily_excess_sigma(px[t], bench, r)
        seed = _seed(sim_cfg["seed"], t)
        sim = simulate(mix, sigma, n_iter=sim_cfg["n_iter"], seed=seed, horizons=tuple(sim_cfg["horizons"]))
        n = int(len(x))
        payload = {
            "schema": 1,
            "ticker": t,
            "group": {"id": g.id, "name": g.name, "benchmark": g.benchmark},
            "asof": asof.date().isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source.name,
            "next_event": next_event(earn[t], asof),
            "sample": {
                "n_events": n,
                "first": r["event_date"].iloc[0] if n else None,
                "last": r["event_date"].iloc[-1] if n else None,
                "group_events": int(len(pooled)),
            },
            "model": {
                "type": "t-mixture-3",
                "ticker": mix.to_dict(),
                "group_prior": prior.to_dict() if prior else None,
                "kappa": mix_cfg["kappa"],
                "tagged": False,
            },
            "gate": {
                "min_events": gate["min_events"],
                "enough_events": n >= gate["min_events"],
                "calibrated": False,  # 백테스트 보정(F10) 전에는 항상 참고용
                "status": "참고용",
            },
            "sim": sim,
            "history": _history(r) if n else [],
            "repro": {
                "seed": seed,
                "n_iter": sim_cfg["n_iter"],
                "data_hash": store.frame_hash(px[[t, g.benchmark]], earn[t]),
                "config_hash": _config_hash(),
                "code_version": __version__,
            },
        }
        p = PUBLISH_DIR / f"{t}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written.append(p)
    return written


def load_published(ticker: str) -> dict | None:
    p = PUBLISH_DIR / f"{ticker}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def record_prediction(ticker: str) -> Path:
    """실적 전 예측을 변경 불가 기록으로 보관 (백테스트·사후 평가용)."""
    pub = load_published(ticker)
    if pub is None:
        raise FileNotFoundError(f"{ticker} 게시 JSON 없음 — 먼저 publish 실행")
    ev = pub.get("next_event")
    if not ev:
        raise ValueError(f"{ticker} 다음 실적일 없음")
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    p = PRED_DIR / f"{ticker}_{ev['date']}_asof{pub['asof']}.json"
    if p.exists():
        return p
    rec = {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ticker": ticker,
        "event": ev,
        "asof": pub["asof"],
        "source": pub["source"],
        "repro": pub["repro"],
        "model": pub["model"],
        "forecast": {h: {k: v for k, v in s.items() if k != "hist"} for h, s in pub["sim"]["horizons"].items()},
        "outcome": None,  # 실적 후 채움
    }
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
