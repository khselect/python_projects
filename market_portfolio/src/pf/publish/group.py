"""그룹 상세(③)·실적 캘린더(②) 게시 JSON (F11·F12·F13).

data/publish/group/{group_id}.json
  heatmap  : 연도×월 동일가중 수익률(월초 리밸런싱 = 구성 종목 월수익률의 평균), 연누적, 벤치마크 연수익률
  car      : 실적 반응일 기준 −5…+63일 누적 초과수익률 평균·25/75 백분위·이벤트 수
  upcoming : 구성 종목의 다음 실적일 (종목 게시 JSON에서)
data/publish/calendar.json
  그룹별 12주 안 발표 예정 종목 + 과거 실적 후 21일 CAR 요약
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pf.config import Group, load_coverage
from pf.events.reactions import event_paths
from pf.publish.ticker import PUBLISH_DIR, _write_json, load_published

GROUP_DIR = PUBLISH_DIR.parent / "group"
CALENDAR_PATH = PUBLISH_DIR.parent / "calendar.json"
CALENDAR_DAYS = 84  # 12주
PRE, POST = 5, 63


def _r(v, nd: int = 5):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def _month_mdd(px: pd.DataFrame, members: list[str]) -> pd.Series:
    """월중 최대 낙폭 (월초 동일 비중으로 산 그룹 포트폴리오, 전달 말 = 1.0에서 시작).

    월말 대비 월말 수익률은 월중에 크게 빠졌다 반등한 달을 가린다 — 그 낙폭을 따로 보여준다.
    """
    ends = px.resample("ME").last().index
    days = px.index
    out = {}
    for prev, cur in zip(ends[:-1], ends[1:]):
        d0 = days[days <= prev]
        if not len(d0):
            continue
        base = px.loc[d0[-1], members]
        win = px.loc[(days > d0[-1]) & (days <= cur), members]
        if win.empty:
            continue
        path = (win / base).mean(axis=1, skipna=True).dropna()
        if path.empty:
            continue
        vals = np.r_[1.0, path.to_numpy()]
        out[cur] = float((vals / np.maximum.accumulate(vals) - 1).min())
    return pd.Series(out)


def _grid(series: pd.Series, years: list[int]) -> list[list]:
    rows = []
    for y in years:
        row = [None] * 12
        for ts, v in series[series.index.year == y].items():
            row[ts.month - 1] = _r(v)
        rows.append(row)
    return rows


def monthly_heatmap(px: pd.DataFrame, members: list[str], bench: str) -> dict:
    """동일가중·월초 리밸런싱 그룹 수익률 + 같은 달 벤치마크 수익률 + 월중 최대 낙폭. 상장 전 종목은 평균에서 빠진다."""
    month_end = px.resample("ME").last()
    mret = month_end.pct_change().iloc[1:]
    grp = mret[members].mean(axis=1, skipna=True)
    bm = mret[bench]
    years = sorted(set(grp.index.year))
    annual, b_annual = [], []
    for y in years:
        annual.append(_r(float(np.prod(1 + grp[grp.index.year == y].dropna()) - 1)))
        b_annual.append(_r(float(np.prod(1 + bm[bm.index.year == y].dropna()) - 1)))
    return {
        "years": years,
        "months": list(range(1, 13)),
        "values": _grid(grp, years),
        "bench_values": _grid(bm, years),
        "mdd": _grid(_month_mdd(px, members), years),
        "annual": annual,
        "bench_annual": b_annual,
        "partial_last_year": bool(px.index[-1].month < 12),
        "weighting": "equal",
    }


def group_car(px: pd.DataFrame, earn: dict[str, pd.DataFrame], members: list[str], bench: str) -> dict:
    paths = []
    for t in members:
        if t in earn and t in px:
            p = event_paths(px[t], px[bench], earn[t], PRE, POST)
            if len(p):
                paths.append(p)
    if not paths:
        return {"n_events": 0}
    allp = pd.concat(paths)
    q = allp.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
    c21 = allp[21 - 1] - allp[-1]  # 반응일(0)~+20 = 21거래일 누적 (반응일 전날까지 빼기)
    return {
        "n_events": int(len(allp)),
        "first": allp.index.min().date().isoformat(),
        "last": allp.index.max().date().isoformat(),
        "days": [int(c) for c in allp.columns],
        "mean": [_r(v) for v in allp.mean()],
        "p25": [_r(v) for v in q.loc[0.25]],
        "p75": [_r(v) for v in q.loc[0.75]],
        "car21": {
            "median": _r(float(c21.median())),
            "p5": _r(float(c21.quantile(0.05))),
            "p95": _r(float(c21.quantile(0.95))),
            "p_down": _r(float((c21 < 0).mean())),
            "n": int(len(c21)),
        },
    }


def upcoming(members: list[str], asof: pd.Timestamp, days: int = CALENDAR_DAYS) -> list[dict]:
    out = []
    for t in members:
        d = load_published(t)
        if not d or not d.get("next_event"):
            continue
        ev = d["next_event"]
        dd = (pd.Timestamp(ev["date"]) - asof).days
        if 0 <= dd <= days:
            h1 = d["sim"]["horizons"]["1"]
            out.append({
                "ticker": t, "date": ev["date"], "timing": ev["timing"], "days": int(dd),
                "p_down": _r(h1["p_down"], 4), "mean": _r(h1["mean"]),
                "p5": _r(h1["pcts"]["5"]), "p95": _r(h1["pcts"]["95"]),
                "n_events": d["sample"]["n_events"],
            })
    return sorted(out, key=lambda e: (e["days"], e["ticker"]))


def publish_groups(px: pd.DataFrame, earn: dict[str, pd.DataFrame]) -> list[Path]:
    """산업·테마 그룹 JSON + 캘린더 JSON. px는 구성 종목·벤치마크 시세(publish_all에서 받은 것)."""
    cov = load_coverage()
    asof = px.index[-1]
    GROUP_DIR.mkdir(parents=True, exist_ok=True)
    written, cal = [], []
    for g in cov.groups:
        members = [t for t in g.members if t in px.columns]
        if g.benchmark not in px.columns or not members:
            continue
        car = group_car(px, earn, members, g.benchmark)
        ups = upcoming(members, asof)
        payload = {
            "schema": 1,
            "group": {"id": g.id, "name": g.name, "kind": g.kind, "benchmark": g.benchmark, "members": members},
            "asof": asof.date().isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "heatmap": monthly_heatmap(px, members, g.benchmark),
            "car": car,
            "upcoming": ups,
            "note": "현재 구성 종목 기준 (과거 시점의 실제 구성과 다를 수 있음)",
        }
        p = GROUP_DIR / f"{g.id}.json"
        _write_json(p, payload, separators=(",", ":"))
        written.append(p)
        cal.append({
            "id": g.id, "name": g.name, "kind": g.kind, "benchmark": g.benchmark,
            "car21": car.get("car21"), "events": ups,
        })
    _write_json(CALENDAR_PATH, {"schema": 1, "asof": asof.date().isoformat(), "max_days": CALENDAR_DAYS, "groups": cal},
                separators=(",", ":"))
    return written


def load_group(group_id: str) -> dict | None:
    import json

    p = GROUP_DIR / f"{group_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
