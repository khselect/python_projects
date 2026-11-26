"""LLM 클라이언트. 맥미니 macOS의 Ollama(HTTP) 또는 오프라인용 가짜 LLM.

새 의존성 없이 urllib만 쓴다. 키 없음, 외부 호출 없음 (Ollama는 host.docker.internal:11434, 외부 비공개).

  PF_AI_BACKEND=ollama | fake | off   (미설정: PF_OFFLINE=1이면 fake, 아니면 ollama)
  OLLAMA_HOST=http://host.docker.internal:11434
"""

from __future__ import annotations

import json
import os
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
        d = self._post("/api/chat", {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": num_ctx},
        }, self.timeout)
        return Reply(d.get("message", {}).get("content", "").strip(), self.model,
                     round(time.perf_counter() - t0, 1), d.get("eval_count", 0), d.get("prompt_eval_count", 0))

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
