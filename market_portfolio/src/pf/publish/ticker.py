"""그룹 단위 실적 반응 계산 → 종목별 게시 JSON (data/publish/ticker/{T}.json).

화면(④ 종목 상세)은 이 JSON만 읽는다. 페이지 조회 시 계산·LLM 호출 없음.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
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


def _write_json(path: Path, payload: dict, **kw) -> None:
    """임시 파일에 쓴 뒤 교체 — 화면이 읽는 도중 반쯤 쓰인 파일을 보지 않게."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, **kw), encoding="utf-8")
    os.replace(tmp, path)


def fetch_earnings(source: Source, ticker: str, max_age_days: float | None = None) -> pd.DataFrame:
    """실적일 표. max_age_days 안에 저장한 캐시가 있으면 재사용 (실적일은 자주 바뀌지 않는다)."""
    if max_age_days is not None:
        p = store.earnings_path(source.name, ticker)
        if p.exists() and time.time() - p.stat().st_mtime < max_age_days * 86400:
            return store.load_earnings(source.name, ticker)
    e = source.earnings(ticker)
    store.save_earnings(source.name, ticker, e)
    return e


def fetch(source: Source, tickers: list[str], use_cache: bool = False, earnings_for: list[str] | None = None):
    """시세는 tickers 전부, 실적일은 earnings_for만 (ETF 벤치마크는 실적이 없다)."""
    px = store.load_prices(source.name) if use_cache else None
    if px is None or not set(tickers) <= set(px.columns):
        px = source.prices(tickers)
        store.save_prices(source.name, px)
    earn = {}
    for t in earnings_for if earnings_for is not None else tickers:
        earn[t] = fetch_earnings(source, t, max_age_days=float("inf") if use_cache else None)
    return px, earn


def publish_group(
    group_id: str,
    source: Source | None = None,
    use_cache: bool = False,
    px: pd.DataFrame | None = None,
    earnings_max_age_days: float | None = None,
) -> list[Path]:
    """그룹 계산·게시. px를 주면 시세를 다시 받지 않는다 (publish_all에서 한 번에 받은 시세)."""
    cov = load_coverage()
    cfg = load_model()
    sim_cfg, mix_cfg, gate = cfg["simulation"], cfg["mixture"], cfg["calibration_gate"]
    g = cov.group(group_id)
    source = source or get_source()

    tickers = list(dict.fromkeys([*g.members, g.benchmark]))
    if px is None:
        px, earn = fetch(source, tickers, use_cache, earnings_for=list(g.members))
    else:
        px = px[tickers].dropna(how="all")
        earn = {t: fetch_earnings(source, t, earnings_max_age_days) for t in g.members}
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
        _write_json(p, payload, separators=(",", ":"))
        written.append(p)
    return written


def publish_all(source: Source | None = None, earnings_max_age_days: float = 3) -> dict:
    """산업 그룹 전체. 시세는 한 번에 받고, 실적일은 max_age 안의 캐시를 재사용한다."""
    cov = load_coverage()
    source = source or get_source()
    tickers = list(dict.fromkeys([t for g in cov.industry for t in (*g.members, g.benchmark)]))
    t0 = time.perf_counter()
    px = source.prices(tickers)
    store.save_prices(source.name, px)
    result = {"source": source.name, "asof": px.index[-1].date().isoformat(), "groups": {}}
    for g in cov.industry:
        try:
            paths = publish_group(g.id, source, px=px, earnings_max_age_days=earnings_max_age_days)
            result["groups"][g.id] = {"ok": True, "tickers": [p.stem for p in paths]}
        except Exception as e:  # 한 그룹 실패가 나머지를 막지 않게
            result["groups"][g.id] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    result["seconds"] = round(time.perf_counter() - t0, 1)
    return result


def due_events(min_days: int = 1, max_days: int = 5) -> list[str]:
    """게시 결과 중 다음 실적이 기준일로부터 min~max일 남은 종목."""
    out = []
    for p in sorted(PUBLISH_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        ev = d.get("next_event")
        if not ev:
            continue
        days = (pd.Timestamp(ev["date"]) - pd.Timestamp(d["asof"])).days
        if min_days <= days <= max_days:
            out.append(d["ticker"])
    return out


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
    _write_json(p, rec, indent=1)
    return p
