"""배치 명령.

  python -m pf.jobs.run daily                                매일 배치: 산업 그룹 10개 + 매크로 국면 + 실적 1~5일 전 예측 기록
  python -m pf.jobs.run macro                                매크로 국면만 계산 (FRED_API_KEY 필요, 오프라인은 합성)
  python -m pf.jobs.run overview                             I. 시장 개요만 계산 (지수·원자재·국채·섹터)
  python -m pf.jobs.run macro-eval                           국면 점수 검증: 스트레스 구간 지연·오경보 (6개 vs 10개 지표)
  python -m pf.jobs.run publish [--group semis] [--cache]   그룹 실적 반응 계산·게시
  python -m pf.jobs.run record AVGO                          실적 전 예측 기록 보관
  python -m pf.jobs.run show AVGO                            게시 JSON 요약 출력 (digest)
  python -m pf.jobs.run ai [--show semis]                    AI 해설 미리 생성만 (Ollama, 오프라인은 가짜 LLM)
  python -m pf.jobs.run ai-bench --models a,b [--contexts 6] 로컬 모델 비교 (같은 근거·검증, 통과율·시간)

컨테이너: docker compose exec market-app python -m pf.jobs.run publish --group semis
"""

from __future__ import annotations

import argparse
import sys
import time

import json
from datetime import datetime, timezone
from pathlib import Path

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


def code_hash() -> str:
    """배치 결과에 영향을 주는 코드(src/pf)와 설정(config/*.yaml)의 해시.

    status.json에 남겨 두고, 스케줄러가 시작할 때 다르면 그날 이미 돌았어도 다시 실행한다
    (새 기능 배포 직후 다음 날 07:15까지 화면이 비던 문제, 2026-11-26).
    """
    import hashlib

    from pf.settings import CONFIG_DIR

    root = Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    files = sorted(root.rglob("*.py")) + sorted(Path(CONFIG_DIR).glob("*.yaml"))
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


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
    try:  # I. 시장 개요 (지수·원자재·국채·섹터) — 실패해도 나머지 결과는 유지
        from pf.publish.overview import publish_overview

        publish_overview()
        overview = {"ok": True}
    except Exception as e:
        overview = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    try:  # 밸류에이션 (재무제표 대기열 + 선행 P/E 누적) — 실패해도 나머지 결과는 유지
        from pf.publish.valuation import publish_valuation

        val = {"ok": True, **publish_valuation()}
    except Exception as e:
        val = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    recorded, rec_err = [], {}
    for t in due_events() if "error" not in res else []:
        try:
            recorded.append(record_prediction(t).name)
        except Exception as e:
            rec_err[t] = f"{type(e).__name__}: {e}"
    try:  # AI 해설 미리 생성 (F20) — 다른 결과가 모두 게시된 뒤. Ollama가 없으면 템플릿으로 채움
        from pf.ai.pregen import pregenerate

        ai = {"ok": True, **pregenerate()}
    except Exception as e:
        ai = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    warnings = [f"{gid}/{w}" for gid, g in res.get("groups", {}).items() for w in g.get("skipped", [])]
    ok = (
        "error" not in res
        and all(g["ok"] for g in res["groups"].values())
        and res.get("group_pages", {"ok": True})["ok"]
        and macro["ok"]
    )
    status = {
        **res,
        "macro": macro,
        "valuation": val,
        "overview": overview,
        "ai": ai,
        "warnings": warnings,
        "code_hash": code_hash(),
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
    for w in warnings:
        print(f"  ⚠️ 건너뜀 {w} (직전 결과 유지)")
    if "error" in res:
        print(f"  ❌ 수집 실패: {res['error']}")
    if not res.get("group_pages", {"ok": True})["ok"]:
        print(f"  ❌ 그룹·캘린더: {res['group_pages']['error']}")
    if val.get("ok"):
        q = val.get("queue") or {}
        print(f"  밸류에이션: 재무 {val.get('have', 0)}/{val.get('total', 0)}종목"
              + (f" · 오늘 받음 {', '.join(q.get('fetched', []))}" if q.get("fetched") else "")
              + (f" · ⚠️ {q['stopped']}" if q.get("stopped") else ""))
    else:
        print(f"  ⚠️ 밸류에이션: {val['error']} (다른 결과에는 영향 없음)")
    if not overview["ok"]:
        print(f"  ⚠️ 시장 개요: {overview['error']} (다른 결과에는 영향 없음)")
    print("  " + ai_line(ai))
    if not macro["ok"]:
        print(f"  ❌ 매크로: {macro['error']}")
    return 0 if ok else 1


def ai_line(ai: dict) -> str:
    if not ai.get("ok"):
        return f"⚠️ AI 해설: {ai['error']} (다른 결과에는 영향 없음)"
    head = f"AI 해설: {ai['backend']}·{ai['model']} · {ai['n']}건 (생성 {ai['ai']}, 재사용 {ai['reused']}, 템플릿 {ai['template']}) · {ai['seconds']}s"
    if not ai["ready"]:
        return f"⚠️ {head} · {ai['why']}"
    if ai.get("digest_errors"):
        head += " · ⚠️ 근거 생성 실패 " + ", ".join(f"{k}({v})" for k, v in ai["digest_errors"].items())
    if ai["reasons"]:
        head += " · 템플릿 사유 " + ", ".join(f"{k} {v}" for k, v in ai["reasons"].items())
    return head


def show_ai(key: str) -> int:
    from pf.ai.pregen import AI_DIR

    hits = sorted(AI_DIR.glob(f"*_{key}.json")) or sorted(AI_DIR.glob(f"*_{key.upper()}.json"))
    if not hits:
        print(f"{key}: AI 해설 없음 ({AI_DIR})")
        return 1
    d = json.loads(hits[0].read_text(encoding="utf-8"))
    print(f"{d['title']} · {d['mode']} · {d.get('model') or '—'} · {d['generated_at']}")
    print(d["text"])
    for a in d.get("attempts", []):
        print("  시도:", a)
    if d.get("reason"):
        print("  템플릿 사유:", d["reason"])
    return 0


def last_status() -> dict | None:
    return json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pf.jobs.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daily")
    sub.add_parser("macro")
    sub.add_parser("overview")
    me = sub.add_parser("macro-eval")
    me.add_argument("--start", default="2007-01-01")
    p = sub.add_parser("publish")
    p.add_argument("--group", default="semis")
    p.add_argument("--cache", action="store_true", help="저장된 원천 데이터 재사용 (네트워크 호출 없음)")
    r = sub.add_parser("record")
    r.add_argument("ticker")
    s = sub.add_parser("show")
    s.add_argument("ticker")
    ab = sub.add_parser("ai-bench")
    ab.add_argument("--models", default="gemma3:4b,qwen2.5:7b-instruct,qwen3:8b")
    ab.add_argument("--contexts", type=int, default=6, help="비교할 해설 근거 수 (많을수록 오래 걸림)")
    ai = sub.add_parser("ai")
    ai.add_argument("--show", help="해설 1건 출력 (macro, 그룹 id, 종목 코드)")
    a = ap.parse_args(argv)

    if a.cmd == "ai-bench":
        from pf.ai.bench import report, run

        print(report(run([m.strip() for m in a.models.split(",") if m.strip()], a.contexts)))
        return 0
    if a.cmd == "ai":
        if a.show:
            return show_ai(a.show)
        from pf.ai.pregen import pregenerate

        print(ai_line({"ok": True, **pregenerate()}))
        return 0

    if a.cmd == "daily":
        return daily()
    if a.cmd == "macro":
        from pf.macro.publish import publish_macro

        print(publish_macro())
        return 0
    if a.cmd == "overview":
        from pf.publish.overview import publish_overview

        print(publish_overview())
        return 0
    if a.cmd == "macro-eval":
        from pf.macro.evaluate import publish_eval, report

        print(report(publish_eval(start=a.start)))
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
