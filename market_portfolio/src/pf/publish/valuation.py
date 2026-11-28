"""밸류에이션 게시 — data/publish/valuation/{group_id}.json (IV. 그룹 상세 밸류에이션 섹션)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pf import valuation as V
from pf.config import load_coverage, load_model
from pf.data import fundamentals as F
from pf.data.sources import Source, get_source
from pf.publish.ticker import PUBLISH_DIR, _write_json

VAL_DIR = PUBLISH_DIR.parent / "valuation"


def _r(v, nd=2):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def priority_symbols() -> list[str]:
    cov = load_coverage()
    pri = load_model()["valuation"]["priority"]
    order = [t for gid in pri for t in cov.group(gid).members] + cov.tickers
    return list(dict.fromkeys(order))


def publish_valuation(source: Source | None = None, fund_client=None, refresh: bool = True) -> dict:
    cfg = load_model()["valuation"]
    cov = load_coverage()
    source = source or get_source()
    symbols = priority_symbols()

    queue = {}
    if refresh:
        try:
            queue = F.refresh(symbols, fund_client, cfg["av_daily_calls"], cfg["max_age_days"])
        except RuntimeError as e:  # 키 없음 등 — 이미 받은 재무로는 계속 게시
            queue = {"stopped": str(e)}
    have = [s for s in symbols if F.load(s) is not None]
    if not have:
        return {"queue": queue, "groups": 0}

    close, splits = source.close_and_splits(have, start=str(int(cfg["start"][:4]) - 2) + "-01-01")
    daily = {t: V.ticker_daily(close[t].dropna(), F.load(t), splits.get(t), cfg["report_lag_days"])
             for t in have if t in close and close[t].notna().any()}

    fwd_note = None
    try:
        snap = source.forward_snapshot(have)
        if len(snap):
            V.append_forward(snap, close.index[-1])
    except Exception as e:
        fwd_note = f"{type(e).__name__}: {e}"
    fwd = V.load_forward()

    VAL_DIR.mkdir(parents=True, exist_ok=True)
    meta = F.load_meta()
    n = 0
    for g in cov.groups:
        members = list(g.members)
        got = {t: daily[t] for t in members if t in daily}
        df = V.group_series(got)
        if len(df):  # 재무가 아직 없는 그룹(대기열 초기)은 빈 표
            df = df[pd.DatetimeIndex(df.index) >= pd.Timestamp(cfg["start"])]
        w = df.resample("W-FRI").last().dropna(subset=["pe", "pfcf"], how="all") if len(df) else df
        latest = []
        for t in members:
            if t not in got or got[t].dropna().empty:
                latest.append({"ticker": t, "missing": True})
                continue
            row = got[t].dropna().iloc[-1]
            latest.append({
                "ticker": t,
                "pe": _r(row["mcap"] / row["ni"]) if row["ni"] > 0 else None,
                "pfcf": _r(row["mcap"] / row["fcf"]) if row["fcf"] > 0 else None,
                "conv": _r(row["fcf"] / row["ni"], 3) if row["ni"] > 0 else None,
                "capex_share": _r(row["capex"] / row["ocf"], 3) if row["ocf"] > 0 else None,
                "fetched_at": meta.get(t, {}).get("fetched_at"),
            })
        fg = V.group_forward_pe(fwd, members)
        ins = V.insight(df) if len(df) else None
        nch = []  # 반영 종목 수가 바뀐 주 — 그래프의 계단 변화가 구성 변화인지 구분
        if len(w):
            nn = w["n"].astype(int)
            for dt, val in nn[nn.ne(nn.shift())].items():
                nch.append({"date": dt.date().isoformat(), "n": int(val)})
        payload = {
            "schema": 1,
            "group": {"id": g.id, "name": g.name},
            "asof": close.index[-1].date().isoformat(),
            "generated_at": V.now_iso(),
            "source": {"fundamentals": next(iter({meta.get(t, {}).get("source") for t in got} - {None}), None), "prices": source.name},
            "coverage": {"have": sorted(got), "missing": [t for t in members if t not in got]},
            "ttm": {
                "dates": [d.date().isoformat() for d in w.index],
                "pe": [_r(v) for v in w["pe"]] if len(w) else [],
                "pfcf": [_r(v) for v in w["pfcf"]] if len(w) else [],
                "gap": [_r(v) for v in w["gap"]] if len(w) else [],
                "conv": [_r(v, 3) for v in w["conv"]] if len(w) else [],
                "capex_share": [_r(v, 3) for v in w["capex_share"]] if len(w) and "capex_share" in w else [],
                "n": [int(v) for v in w["n"]] if len(w) else [],
            },
            "forward_pe": {"dates": [pd.Timestamp(d).date().isoformat() for d in fg.index], "values": [_r(v) for v in fg]},
            "latest": latest,
            "insight": None if ins is None else {k: (_r(v, 4) if isinstance(v, float) else v) for k, v in ins.items()},
            "n_changes": nch[1:] if len(nch) > 1 else [],
            "params": {"report_lag_days": cfg["report_lag_days"]},
            "notes": {"forward_error": fwd_note},
        }
        _write_json(VAL_DIR / f"{g.id}.json", payload, separators=(",", ":"))
        n += 1
    return {"queue": queue, "groups": n, "have": len(have), "total": len(symbols), "forward_error": fwd_note}


def load_valuation(group_id: str) -> dict | None:
    p = VAL_DIR / f"{group_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
