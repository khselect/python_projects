"""LLM 클라이언트. 맥미니 macOS의 Ollama(HTTP) 또는 오프라인용 가짜 LLM.

새 의존성 없이 urllib만 쓴다. 키 없음, 외부 호출 없음 (Ollama는 host.docker.internal:11434, 외부 비공개).

  PF_AI_BACKEND=ollama | fake | off   (미설정: PF_OFFLINE=1이면 fake, 아니면 ollama)
  OLLAMA_HOST=http://host.docker.internal:11434
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from pf.settings import offline


class LLMError(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    model: str
    seconds: float
    eval_count: int = 0
    prompt_count: int = 0

    @property
    def tok_per_s(self) -> float | None:
        return round(self.eval_count / self.seconds, 1) if self.eval_count and self.seconds else None


# 생각(추론) 모드가 기본으로 켜지는 모델 — 끄지 않으면 답 앞에 생각 과정이 붙어 느려지고, 그 안의 숫자 때문에 검증에서 떨어진다
THINKING_FAMILIES = ("qwen3", "deepseek-r1", "qwq")
_THINK_TAG = re.compile(r"<think>.*?</think>", re.S)


def is_thinking_model(model: str) -> bool:
    return model.lower().startswith(THINKING_FAMILIES)


def strip_thinking(text: str) -> str:
    """생각 모드를 끄지 못한 경우(구버전 Ollama) 대비: <think>…</think> 블록과 닫히지 않은 시작 태그 앞부분 제거."""
    text = _THINK_TAG.sub("", text)
    if "<think>" in text:  # 답 길이 한도로 닫는 태그 없이 끊긴 경우 — 답이 없다
        text = text.split("<think>")[0]
    return text.strip()


class OllamaClient:
    name = "ollama"

    def __init__(self, model: str, host: str | None = None, timeout: float = 180):
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://host.docker.internal:11434").rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict, timeout: float) -> dict:
        req = urllib.request.Request(
            self.host + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise LLMError(f"Ollama HTTP {e.code}: {e.read()[:200].decode(errors='replace')}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMError(f"Ollama 연결 실패: {getattr(e, 'reason', e)}") from None

    def available(self) -> tuple[bool, str]:
        """(사용 가능, 사유). 서버가 떠 있고 모델이 받아져 있는지."""
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=5) as r:
                names = {m["name"] for m in json.loads(r.read()).get("models", [])}
        except Exception as e:
            return False, f"Ollama 연결 실패: {getattr(e, 'reason', e)}"
        if self.model not in names and f"{self.model}:latest" not in names:
            return False, f"모델 {self.model} 없음 (ollama pull {self.model})"
        return True, "ok"

    def chat(self, system: str, user: str, *, num_predict: int = 400, temperature: float = 0.2,
             keep_alive: str | int = "5m", num_ctx: int = 4096) -> Reply:
        t0 = time.perf_counter()
        think = is_thinking_model(self.model)
        payload = {
            "model": self.model,
            # qwen3는 메시지 끝 '/no_think'도 생각 모드를 끈다 (구버전 Ollama에서 think 옵션을 무시해도 동작)
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user + (" /no_think" if self.model.lower().startswith("qwen3") else "")}],
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": num_ctx},
        }
        if think:
            payload["think"] = False  # Ollama 0.9+ 생각 모드 끄기
        try:
            d = self._post("/api/chat", payload, self.timeout)
        except LLMError as e:
            if think and "think" in str(e).lower():  # 이 Ollama·모델이 think 옵션을 모르면 옵션 없이 한 번 더
                payload.pop("think", None)
                d = self._post("/api/chat", payload, self.timeout)
            else:
                raise
        text = strip_thinking(d.get("message", {}).get("content", ""))
        return Reply(text, self.model, round(time.perf_counter() - t0, 1), d.get("eval_count", 0), d.get("prompt_eval_count", 0))

    def models(self) -> list[str]:
        """설치된 모델 이름 (실패하면 빈 목록)."""
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=5) as r:
                return sorted(m["name"] for m in json.loads(r.read()).get("models", []))
        except Exception:
            return []

    def unload(self) -> None:
        """모델을 메모리에서 즉시 내린다 (12b 미리 생성 뒤, PLAN §8.1)."""
        try:
            self._post("/api/generate", {"model": self.model, "keep_alive": 0}, 30)
        except LLMError:
            pass


class FakeLLM:
    """오프라인·테스트용. 근거의 앞 사실 몇 줄을 문장으로 이어 붙인다 (항상 검증 통과)."""

    name = "fake"

    def __init__(self, model: str = "fake-template"):
        self.model = model

    def available(self) -> tuple[bool, str]:
        return True, "ok"

    def models(self) -> list[str]:
        from pf.config import load_model

        ai = load_model().get("ai") or {}
        return list(dict.fromkeys([ai.get("chat_model", "gemma3:4b")] + list(ai.get("chat_models") or [])))

    def chat(self, system: str, user: str, **_) -> Reply:
        facts = [l[2:] for l in user.split("[근거]", 1)[-1].split("[용어]", 1)[0].splitlines() if l.startswith("- ")]
        return Reply(" ".join(f"{f.rstrip('.')}입니다." for f in facts[:3]), self.model, 0.0)

    def unload(self) -> None:
        pass


def backend() -> str:
    b = os.environ.get("PF_AI_BACKEND", "").strip().lower()
    return b if b in ("ollama", "fake", "off") else ("fake" if offline() else "ollama")


def get_client(model: str, timeout: float = 180):
    b = backend()
    if b == "off":
        return None
    return FakeLLM() if b == "fake" else OllamaClient(model, timeout=timeout)
