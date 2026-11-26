"""배치 명령.

  python -m pf.jobs.run daily                                매일 배치: 산업 그룹 10개 + 매크로 국면 + 실적 1~5일 전 예측 기록
  python -m pf.jobs.run macro                                매크로 국면만 계산 (FRED_API_KEY 필요, 오프라인은 합성)
  python -m pf.jobs.run publish [--group semis] [--cache]   그룹 실적 반응 계산·게시
  python -m pf.jobs.run record AVGO                          실적 전 예측 기록 보관
  python -m pf.jobs.run show AVGO                            게시 JSON 요약 출력 (digest)

컨테이너: docker compose exec market-app python -m pf.jobs.run publish --group semis
"""

from __future__ import annotations

import argparse
import sys
import time

import json
from datetime import datetime, timezone

from pf.publish.ticker import (
    PUBLISH_DIR,
    _write_json,
    due_events,
    load_published,
    publish_all,
    publish_group,
    record_prediction,
)
from pf.settings import offline


def _pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%"


def show(ticker: str) -> int:
    pub = load_published(ticker)
    if pub is None:
        print(f"{ticker}: 게시 JSON 없음")
        return 1
    h1 = pub["sim"]["horizons"]["1"]
    m = pub["model"]["ticker"]
    print(f"{ticker} ({pub['group']['name']}, 기준일 {pub['asof']}, 출처 {pub['source']})")
    print(f"  다음 실적: {pub['next_event']}")
    print(f"  표본: {pub['sample']['n_events']}건 ({pub['sample']['first']} ~ {pub['sample']['last']}), 그룹 {pub['sample']['group_events']}건")
    print(f"  시나리오: " + ", ".join(
        f"{lab} {w:.0%} 평균 {_pct(mu)} 척도 {s * 100:.1f}%"
        for lab, w, mu, s in zip(m["labels"], m["weights"], m["means"], m["scales"])))
    print(f"  다음 날: P(상승) {h1['p_up']:.0%} · P(하락) {h1['p_down']:.0%} · 기대값 {_pct(h1['mean'])}"
          f" · 90% 구간 {_pct(h1['pcts']['5'])} ~ {_pct(h1['pcts']['95'])} · CVaR5 {_pct(h1['cvar5'])}")
    for h in ("5", "21", "63"):
        s = pub["sim"]["horizons"][h]
        print(f"  {h:>2}일 누적: 중앙값 {_pct(s['pcts']['50'])}, 90% 구간 {_pct(s['pcts']['5'])} ~ {_pct(s['pcts']['95'])}")
    print(f"  재현: {pub['repro']}")
    return 0


STATUS = PUBLISH_DIR.parent / "status.json"


def daily() -> int:
    """매일 배치. 결과는 data/publish/status.json (화면 사이드바·점검용)."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        res = publish_all()
    except Exception as e:  # 시세 수집 자체가 실패한 경우
        res = {"groups": {}, "error": f"{type(e).__name__}: {e}"}
    try:
        from pf.macro.publish import publish_macro

        publish_macro()
        macro = {"ok": True}
    except Exception as e:  # FRED 키 누락·수집 실패가 종목 계산 결과를 막지 않게
        macro = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    recorded, rec_err = [], {}
    for t in due_events() if "error" not in res else []:
        try:
            recorded.append(record_prediction(t).name)
        except Exception as e:
            rec_err[t] = f"{type(e).__name__}: {e}"
    ok = (
        "error" not in res
        and all(g["ok"] for g in res["groups"].values())
        and res.get("group_pages", {"ok": True})["ok"]
        and macro["ok"]
    )
    status = {
        **res,
        "macro": macro,
        "ok": ok,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recorded": recorded,
        "record_errors": rec_err,
    }
    PUBLISH_DIR.parent.mkdir(parents=True, exist_ok=True)
    _write_json(STATUS, status, indent=1)
    n = sum(len(g.get("tickers", [])) for g in res["groups"].values())
    print(f"[daily] {'OK' if ok else '실패 있음'} · 기준일 {res.get('asof', '—')} · {n}종목 · {res.get('seconds', '—')}s · 기록 {recorded or '없음'}")
    for gid, g in res["groups"].items():
        if not g["ok"]:
            print(f"  ❌ {gid}: {g['error']}")
    if "error" in res:
        print(f"  ❌ 수집 실패: {res['error']}")
    if not res.get("group_pages", {"ok": True})["ok"]:
        print(f"  ❌ 그룹·캘린더: {res['group_pages']['error']}")
    if not macro["ok"]:
        print(f"  ❌ 매크로: {macro['error']}")
    return 0 if ok else 1


def last_status() -> dict | None:
    return json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pf.jobs.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daily")
    sub.add_parser("macro")
    p = sub.add_parser("publish")
    p.add_argument("--group", default="semis")
    p.add_argument("--cache", action="store_true", help="저장된 원천 데이터 재사용 (네트워크 호출 없음)")
    r = sub.add_parser("record")
    r.add_argument("ticker")
    s = sub.add_parser("show")
    s.add_argument("ticker")
    a = ap.parse_args(argv)

    if a.cmd == "daily":
        return daily()
    if a.cmd == "macro":
        from pf.macro.publish import publish_macro

        print(publish_macro())
        return 0
    if a.cmd == "publish":
        t0 = time.perf_counter()
        paths = publish_group(a.group, use_cache=a.cache)
        mode = "합성(PF_OFFLINE=1)" if offline() else "실데이터"
        print(f"[{mode}] {a.group}: {len(paths)}종목 게시 ({time.perf_counter() - t0:.1f}s)")
        for p in paths:
            print(f"  {p} ({p.stat().st_size / 1024:.1f}KB)")
        return 0
    if a.cmd == "record":
        print(record_prediction(a.ticker.upper()))
        return 0
    return show(a.ticker.upper())


if __name__ == "__main__":
    sys.exit(main())
