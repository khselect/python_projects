"""AI 모델 비교 (ai-bench). 같은 근거·같은 검증으로 여러 로컬 모델을 돌려 통과율·속도를 잰다.

  python -m pf.jobs.run ai-bench --models gemma3:4b,qwen2.5:7b-instruct,qwen3:8b [--contexts 6]

두 가지를 잰다:
  해설  : 미리 생성 해설과 같은 근거(오늘 digest) n건 → 첫 시도 통과·최종 통과·탈락 사유·시간
  질문  : config/ai_questions.yaml 고정 질문 → 기대(answer/unanswerable/refuse)와 맞는지·검증 통과·시간
결과 data/ai/bench/<시각>.json. 모델마다 끝나면 메모리에서 내린다(16GB 보호).
판정 기준은 사이트와 같은 guard — 모델이 바뀌어도 기준은 같다.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone

import yaml

from pf.ai import guard
from pf.ai.client import get_client
from pf.ai.pregen import SYSTEM as PREGEN_SYSTEM, USER_TAIL, contexts, generate_one
from pf.ai.qa import UNANSWERABLE, answer, qa_config
from pf.settings import CONFIG_DIR, DATA_DIR

BENCH_DIR = DATA_DIR / "ai" / "bench"


def load_questions() -> list[dict]:
    return yaml.safe_load((CONFIG_DIR / "ai_questions.yaml").read_text(encoding="utf-8"))["questions"]


def _digest_for(page: str, ds: dict):
    """page 문자열 → 오늘 digest (contexts()에서 만든 것 재사용)."""
    kind, _, key = page.partition(":")
    key = key or kind
    return ds.get((kind, key))


def run(models: list[str], n_contexts: int = 6, log=print) -> dict:
    base_cfg = qa_config()
    all_ds = contexts(base_cfg["max_tickers"], base_cfg["ticker_days"])
    by_key = {(d.kind, d.key): d for d in all_ds}
    pre = all_ds[:n_contexts]
    qs = load_questions()
    out = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "n_contexts": len(pre),
           "n_questions": len(qs), "models": {}}
    for m in models:
        client = get_client(m, timeout=base_cfg["pregen_timeout_s"])
        ok, why = client.available() if client else (False, "AI 꺼짐")
        if not ok:
            log(f"[{m}] 건너뜀: {why}")
            out["models"][m] = {"skipped": why}
            continue
        cfg = {**base_cfg, "chat_model": m, "chat_keep_alive": "10m", "chat_keep_alive_other": "10m", "global_daily": 10**9}
        t0 = time.perf_counter()
        # 1) 해설 (미리 생성과 같은 경로)
        pr = []
        for d in pre:
            r = generate_one(client, d, cfg)
            first = (r["attempts"] or [{}])[0]
            pr.append({"key": f"{d.kind}:{d.key}", "mode": r["mode"], "first_ok": not first.get("issues") and "error" not in first,
                       "issues": [i.split(":")[0] for a in r["attempts"] for i in a.get("issues", [])],
                       "seconds": sum(a.get("seconds", 0) for a in r["attempts"]), "text": r["text"][:300]})
            log(f"[{m}] 해설 {d.kind}:{d.key} → {r['mode']} ({pr[-1]['seconds']:.0f}s)")
        # 2) 질문
        qr = []
        for q in qs:
            d = _digest_for(q["page"], by_key)
            if d is None:
                qr.append({"q": q["q"], "page": q["page"], "skipped": "근거 없음"})
                continue
            r = answer(q["q"], d, client, cfg, log=False)
            said_cant = UNANSWERABLE in (r.get("text") or "")
            exp = q["expect"]
            hit = (r["mode"] == "refused") if exp == "refuse" else \
                  (r["mode"] == "ai" and said_cant) if exp == "unanswerable" else \
                  (r["mode"] == "ai" and not said_cant)
            qr.append({"q": q["q"], "page": q["page"], "expect": exp, "mode": r["mode"], "hit": hit,
                       "first_ok": bool(r.get("attempts")) and not r["attempts"][0].get("issues"),
                       "seconds": r.get("seconds"), "text": (r.get("text") or "")[:300]})
            log(f"[{m}] 질문 {q['q'][:20]}… → {r['mode']} {'✓' if hit else '✗'} ({r.get('seconds')}s)")
        client.unload()
        llm_q = [x for x in qr if x.get("expect") in ("answer", "unanswerable")]
        secs = [x["seconds"] for x in pr] + [x["seconds"] for x in llm_q if x.get("seconds")]
        out["models"][m] = {
            "pregen_first_pass": sum(x["first_ok"] for x in pr) / max(len(pr), 1),
            "pregen_final_pass": sum(x["mode"] == "ai" for x in pr) / max(len(pr), 1),
            "qa_expected": sum(x.get("hit", False) for x in llm_q) / max(len(llm_q), 1),
            "qa_first_pass": sum(x.get("first_ok", False) for x in llm_q) / max(len(llm_q), 1),
            "refusal_rule": all(x["hit"] for x in qr if x.get("expect") == "refuse"),
            "median_seconds": statistics.median(secs) if secs else None,
            "issue_counts": _count([i for x in pr for i in x["issues"]]),
            "total_seconds": round(time.perf_counter() - t0, 1),
            "pregen": pr, "questions": qr,
        }
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    path = BENCH_DIR / (out["at"].replace(":", "")[:15] + ".json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    out["path"] = str(path)
    return out


def _count(xs: list[str]) -> dict:
    d: dict[str, int] = {}
    for x in xs:
        d[x] = d.get(x, 0) + 1
    return d


def report(res: dict) -> str:
    lines = [f"AI 모델 비교 · 해설 {res['n_contexts']}건 + 질문 {res['n_questions']}개 · 같은 근거·같은 검증",
             f"{'모델':<22} {'해설 첫시도':>9} {'해설 최종':>8} {'질문 기대일치':>11} {'질문 첫시도':>10} {'중앙 시간':>8}  탈락 사유"]
    for m, r in res["models"].items():
        if "skipped" in r:
            lines.append(f"{m:<22} 건너뜀 — {r['skipped']}")
            continue
        iss = ", ".join(f"{k} {v}" for k, v in r["issue_counts"].items()) or "없음"
        lines.append(f"{m:<22} {r['pregen_first_pass']:>9.0%} {r['pregen_final_pass']:>8.0%} {r['qa_expected']:>11.0%} "
                     f"{r['qa_first_pass']:>10.0%} {r['median_seconds'] or 0:>7.1f}s  {iss}")
    lines.append("해설 첫시도 = 재시도 없이 검증 통과 · 질문 기대일치 = 답해야 할 건 답하고, 근거 밖은 '답할 수 없습니다' · "
                 "범위 밖 질문은 규칙으로 거절(모델 무관)")
    lines.append(f"자세한 답변: {res.get('path', '')}")
    return "\n".join(lines)
