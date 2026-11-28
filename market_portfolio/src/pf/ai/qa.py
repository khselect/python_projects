"""F20 2단계 — 자유 질문 (오른쪽 종합 인사이트 패널). 로컬 Ollama (기본 qwen3:8b, model.yaml ai.chat_model).

흐름: 질문 길이·한도 확인 → 범위 밖(매수·매도·비중·목표가)이면 LLM 없이 거절
     → 근거 = 지금 보는 화면의 digest + 질문과 관련된 용어 설명
     → LLM → guard 검증(근거·질문에 없는 숫자·날짜, 금지어, 길이) → 실패 시 사유를 알려 1회 재시도
     → 그래도 실패하면 답 대신 '근거 요약'. 검증 전 문장은 화면에 내지 않는다(스트리밍하지 않는 이유).
질문 기록(data/ai/qa/날짜.jsonl)은 3단계 골든 세트·평가용. 이메일·전화번호 형태는 지우고 저장한다.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from pf.ai import guard
from pf.ai.client import LLMError
from pf.ai.digest import Digest
from pf.config import load_glossary
from pf.settings import DATA_DIR

QA_DIR = DATA_DIR / "ai" / "qa"

SYSTEM = """너는 market.sielain.com 대시보드의 질문 도우미다. 사용자가 보고 있는 화면에 대한 질문에 [근거]와 [용어]만 써서 한국어로 답한다.
규칙:
1. 숫자와 날짜는 [근거]·[용어]·질문에 적힌 값만 그대로 옮긴다. 계산하거나 새 숫자를 만들지 않는다.
2. [근거]·[용어]로 답할 수 없는 질문이면 "이 화면의 자료로는 답할 수 없습니다"라고 말하고, 대신 볼 만한 지표를 하나 알려준다.
3. 뉴스·사건·전망·원인을 지어내지 않는다.
4. 투자 행동(매수·매도·비중·목표가)을 권하지 않는다. 명령형 표현과 '반드시', '확실히', '보장'을 쓰지 않는다.
5. 확률이나 기대값을 말하면 손실 쪽 숫자(90% 구간 하단 등)가 근거에 있을 때 함께 말한다.
6. 서술형 '~입니다'체, 2~5문장, 제목·목록·마크다운 없이 답한다."""

FALLBACK = "검증을 통과한 답을 만들지 못해 이 화면의 근거 일부를 대신 보여드립니다: "
UNANSWERABLE = "이 화면의 자료로는 답할 수 없습니다"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"\d{2,3}-\d{3,4}-\d{4}")


def qa_config() -> dict:
    from pf.ai.pregen import ai_config

    d = {"chat_timeout_s": 60, "chat_num_predict": 400, "chat_keep_alive": "30m", "session_daily": 10,
         "global_daily": 600, "max_question_chars": 500, "queue_max": 3, "evidence_chars": 3500,
         "chat_models": ["gemma3:4b"], "chat_keep_alive_other": "5m"}
    return {**d, **ai_config()}


# ── 근거: 화면 digest + 질문 관련 용어 ──────────────────────────

def related_terms(question: str, limit: int = 4) -> list[str]:
    """질문에 용어 이름·키가 들어 있으면 그 용어의 설명(body)을 근거에 넣는다."""
    g = load_glossary()
    q = question.replace(" ", "").lower()
    hits = []
    for k, v in g.items():
        label = str(v.get("label", "")).replace(" ", "")
        names = {label.lower(), k.lower()} | {label.split("(")[0].lower()}
        if any(n and n in q for n in names):
            hits.append(f"{v['label']}: {' '.join(str(v.get('body') or v.get('tip')).split())}")
    return hits[:limit]


def evidence(d: Digest, question: str, max_chars: int = 3500) -> str:
    terms = related_terms(question)
    base = Digest(d.kind, d.key, d.title, d.asof, d.facts, list(dict.fromkeys(terms + d.terms)), d.sources)
    text = base.text()
    return text if len(text) <= max_chars else text[:max_chars]


# ── 한도: 세션(화면 쪽), 전체 하루, 동시 1건 + 대기열 ────────────

class Gate:
    """동시에 LLM 1건, 대기 최대 queue_max건 (OLLAMA_NUM_PARALLEL=1과 같은 가정)."""

    def __init__(self, queue_max: int = 3):
        self.sem = threading.Semaphore(1)
        self.lock = threading.Lock()
        self.waiting = 0
        self.queue_max = queue_max

    def __enter__(self):
        with self.lock:
            if self.waiting >= self.queue_max:
                raise Busy()
            self.waiting += 1
        self.sem.acquire()
        with self.lock:
            self.waiting -= 1
        return self

    def __exit__(self, *exc):
        self.sem.release()


class Busy(RuntimeError):
    pass


def _usage_path() -> Path:
    return QA_DIR / "usage.json"


def global_used(today: str | None = None) -> int:
    today = today or datetime.now(timezone.utc).date().isoformat()
    p = _usage_path()
    if not p.exists():
        return 0
    d = json.loads(p.read_text(encoding="utf-8"))
    return int(d.get(today, 0))


def _bump(today: str) -> None:
    p = _usage_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    d = {today: int(d.get(today, 0)) + 1}  # 오늘 것만 남긴다
    p.write_text(json.dumps(d), encoding="utf-8")


def redact(text: str) -> str:
    return _PHONE.sub("[전화번호]", _EMAIL.sub("[이메일]", text))


def _log(rec: dict) -> None:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    day = rec["at"][:10]
    with (QA_DIR / f"{day}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── 답변 ───────────────────────────────────────────────────

def fallback_text(d: Digest) -> str:
    return FALLBACK + " ".join(f"{x.rstrip('.')}." for x in d.facts[:2])


def answer(question: str, d: Digest, client, cfg: dict | None = None, gate: Gate | None = None,
           log: bool = True) -> dict:
    """반환: {mode: ai|refused|fallback|limit|busy|error, text, seconds, issues, model, evidence}"""
    cfg = cfg or qa_config()
    t0 = time.perf_counter()
    q = question.strip()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    base = {"question": redact(q)[:cfg["max_question_chars"]], "page": f"{d.kind}:{d.key}", "at": now.isoformat(timespec="seconds"),
            "llm": getattr(client, "model", None)}
    keep = cfg["chat_keep_alive"] if getattr(client, "model", None) == cfg["chat_model"] else cfg["chat_keep_alive_other"]

    def done(res: dict) -> dict:
        res["seconds"] = round(time.perf_counter() - t0, 1)
        if log:
            _log({**base, **{k: v for k, v in res.items() if k != "evidence"}})
        return res

    if not q:
        return {"mode": "limit", "text": "질문을 입력해 주세요."}
    if len(q) > cfg["max_question_chars"]:
        return done({"mode": "limit", "text": f"질문은 {cfg['max_question_chars']}자 이내로 써 주세요."})
    if guard.out_of_scope(q):
        return done({"mode": "refused", "text": guard.REFUSAL})
    if global_used(today) >= cfg["global_daily"]:
        return done({"mode": "limit", "text": "오늘 전체 질문 한도에 도달했습니다. 내일 다시 이용해 주세요."})
    if client is None:
        return done({"mode": "error", "text": "AI 해설이 꺼져 있습니다."})

    ev = evidence(d, q, cfg["evidence_chars"])
    allowed_text = ev + "\n" + q  # 질문에 나온 숫자를 되받아 쓰는 것은 허용
    user = f"{ev}\n\n[질문] {q}"
    attempts = []
    try:
        with (gate or Gate(cfg["queue_max"])):
            _bump(today)
            for i in range(2):
                try:
                    r = client.chat(SYSTEM, user, num_predict=cfg["chat_num_predict"],
                                    temperature=cfg["temperature"] if i == 0 else 0.0,
                                    keep_alive=keep)
                except LLMError as e:
                    attempts.append({"error": str(e)})
                    return done({"mode": "error", "text": "지금 AI에 연결할 수 없습니다. 잠시 뒤 다시 시도해 주세요.",
                                 "issues": [str(e)], "attempts": attempts, "evidence": ev})
                issues = guard.check(r.text, allowed_text)
                if UNANSWERABLE in r.text:
                    issues = [i for i in issues if i != "너무 짧음"]
                attempts.append({"issues": issues, "seconds": r.seconds, "tokens": r.eval_count})
                if not issues:
                    return done({"mode": "ai", "text": r.text, "model": r.model, "attempts": attempts, "evidence": ev})
                user = (f"{ev}\n\n[질문] {q}\n\n직전 답변은 다음 문제로 반려되었다: {'; '.join(issues)}. "
                        "근거에 있는 숫자만 그대로 쓰고 다시 답하라.")
    except Busy:
        return done({"mode": "busy", "text": "지금 질문이 많아 대기열이 찼습니다. 잠시 뒤 다시 시도해 주세요."})
    return done({"mode": "fallback", "text": fallback_text(d), "issues": attempts[-1]["issues"],
                 "attempts": attempts, "evidence": ev})
