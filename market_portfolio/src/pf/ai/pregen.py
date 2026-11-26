"""AI 해설 미리 생성 (F20 1단계). 매일 배치 끝에서 실행 → data/publish/ai/*.json.

화면은 이 JSON을 읽기만 한다 (페이지 조회당 LLM 호출 0).
흐름: digest(코드) → LLM 문장화 → guard 검증 → 실패 시 1회 재시도 → 그래도 실패면 템플릿.
Ollama가 꺼져 있어도 템플릿으로 채워져 화면은 항상 정상이다.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pandas as pd

from pf.ai import guard
from pf.ai.client import LLMError, get_client
from pf.ai.digest import Digest, group_digest, macro_digest, ticker_digest
from pf.config import load_coverage, load_model
import pf.macro.publish as mpub
import pf.publish.ticker as tpub
from pf.publish.group import load_group
from pf.publish.ticker import PUBLISH_DIR, _write_json
from pf.publish.valuation import load_valuation

AI_DIR = PUBLISH_DIR.parent / "ai"
PROMPT_VERSION = 1  # 프롬프트를 바꾸면 올린다 → 근거가 같아도 다시 생성

SYSTEM = """너는 market.sielain.com 대시보드의 해설 도우미다. 사용자가 보고 있는 화면을 [근거]의 사실만으로 한국어로 풀어 설명한다.
규칙:
1. 숫자와 날짜는 [근거]에 적힌 값을 그대로 옮긴다. 계산하거나 반올림을 바꾸거나 새 숫자를 만들지 않는다.
2. [근거]에 없는 뉴스·사건·전망·원인을 덧붙이지 않는다.
3. 투자 행동(매수·매도·비중·목표가)을 권하지 않는다. 명령형 표현과 '반드시', '확실히', '보장'을 쓰지 않는다.
4. 기대값이나 확률을 말하면 손실 쪽 숫자(90% 구간 하단 등)도 함께 말한다.
5. 서술형 '~입니다'체, 3~5문장, 제목·목록·마크다운 없이 문단 하나로 쓴다."""

USER_TAIL = "\n\n위 근거만 사용해 이 화면의 현재 상태를 3~5문장으로 해설하라."


def ai_config() -> dict:
    d = {"pregen_model": "gemma3:12b", "chat_model": "gemma3:4b", "pregen_timeout_s": 180,
         "pregen_budget_s": 1500, "max_tickers": 5, "ticker_days": 14, "num_predict": 400, "temperature": 0.2}
    return {**d, **(load_model().get("ai") or {})}


def _load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def contexts(max_tickers: int = 5, ticker_days: int = 14) -> list[Digest]:
    """오늘 만들 해설 대상: 매크로 1 + 그룹(산업 10 + 테마) + 실적이 가까운 종목 몇 개."""
    macro = _load_json(mpub.MACRO_PATH)  # 모듈 속성으로 읽는다 (테스트에서 경로 교체)
    out: list[Digest] = []
    if macro:
        out.append(macro_digest(macro))
    for g in load_coverage().groups:
        grp = load_group(g.id)
        if grp:
            out.append(group_digest(grp, load_valuation(g.id), macro))
    near = []
    for p in sorted(tpub.PUBLISH_DIR.glob("*.json")):
        t = json.loads(p.read_text(encoding="utf-8"))
        ev = t.get("next_event")
        if ev:
            days = (pd.Timestamp(ev["date"]) - pd.Timestamp(t["asof"])).days
            if 0 <= days <= ticker_days:
                near.append((days, t))
    for _, t in sorted(near, key=lambda x: (x[0], x[1]["ticker"]))[:max_tickers]:
        out.append(ticker_digest(t, load_group(t["group"]["id"]), macro))
    return out


def template_text(d: Digest) -> str:
    """LLM을 쓸 수 없을 때의 문장 (근거 앞 3줄)."""
    return " ".join(f"{f.rstrip('.')}입니다." for f in d.facts[:3])


def path_for(kind: str, key: str):
    return AI_DIR / f"{kind}_{key}.json"


def generate_one(client, d: Digest, cfg: dict) -> dict:
    """LLM 1회 + 검증 실패 시 문제를 알려주고 1회 재시도. 둘 다 실패하면 템플릿."""
    ev = d.text()
    user = ev + USER_TAIL
    attempts = []
    for i in range(2):
        try:
            r = client.chat(SYSTEM, user, num_predict=cfg["num_predict"],
                            temperature=cfg["temperature"] if i == 0 else 0.0)
        except LLMError as e:
            attempts.append({"error": str(e)})
            break  # 연결·시간 초과는 재시도해도 같다
        issues = guard.check(r.text, ev)
        attempts.append({"issues": issues, "seconds": r.seconds, "tokens": r.eval_count, "tok_per_s": r.tok_per_s})
        if not issues:
            return {"mode": "ai", "text": r.text, "model": r.model, "attempts": attempts}
        user = (ev + USER_TAIL + "\n\n직전 답변은 다음 문제로 반려되었다: " + "; ".join(issues)
                + ". 근거의 숫자만 그대로 쓰고 다시 작성하라.")
    reason = attempts[-1].get("error") or "검증 실패: " + "; ".join(attempts[-1]["issues"])
    return {"mode": "template", "text": template_text(d), "model": None, "reason": reason, "attempts": attempts}


def pregenerate(client="auto", cfg: dict | None = None) -> dict:
    """오늘 해설 생성. 반환: 상태 요약 (status.json의 ai 항목)."""
    cfg = cfg or ai_config()
    t0 = time.perf_counter()
    if client == "auto":
        client = get_client(cfg["pregen_model"], timeout=cfg["pregen_timeout_s"])
    ready, why = client.available() if client else (False, "AI 해설 꺼짐 (PF_AI_BACKEND=off)")
    AI_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = {"ai": 0, "reused": 0, "template": 0}
    reasons: dict[str, int] = {}
    keep = set()
    ds = contexts(cfg["max_tickers"], cfg["ticker_days"])
    for d in ds:
        p = path_for(d.kind, d.key)
        keep.add(p.name)
        h = f"{d.hash()}-p{PROMPT_VERSION}"
        old = _load_json(p)
        if old and old.get("digest_hash") == h and old.get("mode") == "ai" and ready:
            counts["reused"] += 1  # 근거·프롬프트가 같으면 다시 만들지 않는다 (배포 직후 재실행 대비)
            continue
        if not ready:
            res = {"mode": "template", "text": template_text(d), "model": None, "reason": why, "attempts": []}
        elif time.perf_counter() - t0 > cfg["pregen_budget_s"]:
            res = {"mode": "template", "text": template_text(d), "model": None, "reason": "배치 시간 예산 초과", "attempts": []}
        else:
            res = generate_one(client, d, cfg)
        counts["ai" if res["mode"] == "ai" else "template"] += 1
        if res["mode"] == "template":
            key = res["reason"].split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1
        _write_json(p, {
            "schema": 1, "kind": d.kind, "key": d.key, "title": d.title, "asof": d.asof,
            "generated_at": now, "digest_hash": h, "facts": d.facts, "terms": d.terms, "sources": d.sources,
            **res,
        }, indent=1)
    for f in AI_DIR.glob("*.json"):  # 오늘 대상이 아닌 해설(실적이 지난 종목 등)은 지운다
        if f.name not in keep:
            f.unlink()
    if client and ready:
        client.unload()
    return {
        "backend": getattr(client, "name", "off"), "model": getattr(client, "model", None),
        "ready": ready, "why": None if ready else why, "n": len(ds), **counts, "reasons": reasons,
        "seconds": round(time.perf_counter() - t0, 1),
    }


def load_ai(kind: str, key: str) -> dict | None:
    return _load_json(path_for(kind, key))
