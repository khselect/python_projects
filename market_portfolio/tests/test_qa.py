"""F20 2단계: 자유 질문 — 범위 밖 거절(LLM 미호출), 근거 대조, 재시도, 한도, 대기열, 기록."""

import json

import pytest

import pf.ai.qa as QA
from pf.ai.client import FakeLLM, LLMError, Reply
from pf.ai.digest import Digest

D = Digest("macro", "macro", "II. 매크로 국면", "2026-11-25",
           ["국면 점수 -1 (범위 −10~+10), 국면 '위험회피(급변)', 2026-11-20부터",
            "[시장 층] VIX: 비우호, VIX 28.3 (최근 1개월 최고 35.9)"],
           ["국면 점수: 10개 지표의 합(−10~+10)"])
GOOD = "국면 점수는 -1이고 국면은 '위험회피(급변)'입니다. VIX는 28.3으로 최근 1개월 최고 35.9보다 낮지만 비우호 구간입니다."


class Scripted:
    name, model = "scripted", "scripted"

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def chat(self, system, user, **kw):
        self.calls.append(user)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return Reply(a, self.model, 1.0, 50)


@pytest.fixture(autouse=True)
def qa_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(QA, "QA_DIR", tmp_path / "qa")
    return tmp_path / "qa"


CFG = {**QA.qa_config(), "global_daily": 3}


@pytest.mark.parametrize("q", ["지금 반도체 사도 돼?", "비중 얼마나 줄여야 해?", "AVGO 목표가 알려줘"])
def test_out_of_scope_refused_without_llm(q):
    llm = Scripted()
    r = QA.answer(q, D, llm, CFG)
    assert r["mode"] == "refused" and not llm.calls


def test_grounded_answer_passes():
    r = QA.answer("국면 점수가 왜 -1이야?", D, Scripted(GOOD), CFG)
    assert r["mode"] == "ai" and r["text"] == GOOD and "[질문]" not in r["text"]


def test_numbers_from_question_allowed():
    ans = "VIX 30은 급변 규칙의 기준입니다. 지금 VIX는 28.3이고 최근 1개월 최고는 35.9입니다."
    r = QA.answer("VIX가 30을 넘으면 어떻게 돼?", D, Scripted(ans), CFG)
    assert r["mode"] == "ai"


def test_invented_number_retry_then_fallback():
    llm = Scripted(GOOD.replace("28.3", "31.0"), GOOD.replace("35.9", "44.4"))
    r = QA.answer("VIX는 지금 어때?", D, llm, CFG)
    assert r["mode"] == "fallback" and len(llm.calls) == 2 and "근거에 없는 숫자" in llm.calls[1]
    assert r["text"].startswith(QA.FALLBACK)


def test_unanswerable_short_reply_ok():
    r = QA.answer("내일 FOMC 결과는?", D, Scripted("이 화면의 자료로는 답할 수 없습니다. 대신 국면 점수를 보세요."), CFG)
    assert r["mode"] == "ai"


def test_connection_error_message():
    r = QA.answer("국면 점수는?", D, Scripted(LLMError("Ollama 연결 실패")), CFG)
    assert r["mode"] == "error" and "연결" in r["text"]


def test_limits_length_and_global_daily():
    assert QA.answer("가" * 600, D, Scripted(), CFG)["mode"] == "limit"
    for _ in range(3):
        assert QA.answer("국면 점수는?", D, Scripted(GOOD), CFG)["mode"] == "ai"
    assert QA.answer("국면 점수는?", D, Scripted(GOOD), CFG)["mode"] == "limit"  # 전체 하루 3건


def test_gate_rejects_when_queue_full():
    g = QA.Gate(queue_max=0)
    with pytest.raises(QA.Busy):
        with g:
            pass


def test_related_terms_and_evidence_budget():
    terms = QA.related_terms("VIX가 뭐야? 급변 규칙은?")
    assert any(t.startswith("VIX") for t in terms) and any(t.startswith("급변 규칙") for t in terms)
    ev = QA.evidence(D, "VIX가 뭐야?", max_chars=200)
    assert len(ev) <= 200


def test_log_redacts_personal_info(qa_dir):
    QA.answer("제 이메일 a.b@test.com, 010-1234-5678 인데 국면 점수는?", D, Scripted(GOOD), CFG)
    rec = json.loads(next(qa_dir.glob("2*.jsonl")).read_text(encoding="utf-8").splitlines()[-1])
    assert "a.b@test.com" not in rec["question"] and "010-1234-5678" not in rec["question"]
    assert "[이메일]" in rec["question"] and rec["mode"] == "ai" and "evidence" not in rec


def test_fake_llm_offline_answer_passes():
    r = QA.answer("국면 점수가 뭐야?", D, FakeLLM(), CFG)
    assert r["mode"] == "ai"


def test_thinking_off_for_qwen3_and_strip(monkeypatch):
    from pf.ai.client import OllamaClient, strip_thinking

    sent = []

    def fake_post(self, path, payload, timeout):
        sent.append(payload)
        return {"message": {"content": "<think>내부 생각 123</think>국면 점수는 -1입니다."}, "eval_count": 5}

    monkeypatch.setattr(OllamaClient, "_post", fake_post)
    r = OllamaClient("qwen3:8b").chat("s", "질문")
    assert sent[0]["think"] is False and sent[0]["messages"][1]["content"].endswith("/no_think")
    assert r.text == "국면 점수는 -1입니다."  # 생각 블록 제거
    OllamaClient("gemma3:4b").chat("s", "질문")
    assert "think" not in sent[1] and not sent[1]["messages"][1]["content"].endswith("/no_think")
    assert strip_thinking("<think>끊긴 생각") == ""


def test_think_option_unsupported_falls_back(monkeypatch):
    from pf.ai.client import OllamaClient

    calls = []

    def fake_post(self, path, payload, timeout):
        calls.append(dict(payload))
        if "think" in payload:
            raise LLMError('Ollama HTTP 400: {"error":"registry.ollama.ai/library/qwen3:8b does not support thinking"}')
        return {"message": {"content": "답"}, "eval_count": 1}

    monkeypatch.setattr(OllamaClient, "_post", fake_post)
    assert OllamaClient("qwen3:8b").chat("s", "q").text == "답" and len(calls) == 2


def test_non_default_model_short_keep_alive():
    seen = {}

    class Rec(Scripted):
        model = "qwen3:8b"

        def chat(self, system, user, **kw):
            seen.update(kw)
            return Reply(GOOD, self.model, 1.0, 50)

    QA.answer("국면 점수는?", D, Rec(), {**CFG, "chat_model": "gemma3:4b"})
    assert seen["keep_alive"] == CFG["chat_keep_alive_other"]


def test_bench_offline_smoke(tmp_path, monkeypatch):
    import pf.ai.bench as B

    monkeypatch.setattr(B, "BENCH_DIR", tmp_path / "bench")
    monkeypatch.setattr(B, "contexts", lambda *a, **k: [D])
    res = B.run(["fake-a"], n_contexts=1, log=lambda *_: None)
    r = res["models"]["fake-a"]
    assert r["pregen_final_pass"] == 1.0 and r["refusal_rule"] is True
    assert (tmp_path / "bench").glob("*.json") and "fake-a" in B.report(res)


def test_targets_groups_tickers_aliases():
    t = {(k, key) for k, key, _ in QA.targets("반도체 산업은 2026년 수익률 비교시 10년 평균보다 높았어?")}
    assert t == {("group", "semis")}
    assert ("ticker", "NVDA") in {(k, key) for k, key, _ in QA.targets("엔비디아 실적 반응은?")}
    assert QA.targets("국면 점수는?") == []


SEMIS = Digest("group", "semis", "IV. 그룹 상세 — 반도체", "2026-11-25",
               ["2026년(1~11월, 진행 중) 그룹 수익률 +0.6% — 과거 10년 같은 기간 평균 +15.5%보다 낮음"])


def test_routed_evidence_first_and_copied_format_rejected():
    """11-28 운영: II 화면에서 반도체를 물었더니 근거에 반도체가 없고, 모델이 [근거] 줄을 복사한 답이 검증을 통과."""
    bad = "[근거] 2026-11-25 기준, [시장 층] VIX 28.3\n[용어] 국면 점수: 10개 지표의 합"
    good = "반도체 그룹의 2026년(1~11월, 진행 중) 수익률은 +0.6%로, 과거 10년 같은 기간 평균 +15.5%보다 낮습니다."
    llm = Scripted(bad, good)
    r = QA.answer("반도체 산업은 2026년 수익률 비교시 10년 평균보다 높았어?", D, llm, CFG, extra=[SEMIS])
    assert r["mode"] == "ai" and r["text"] == good and r["routed"] == ["group:semis"]
    assert llm.calls[0].index("반도체") < llm.calls[0].index("II. 매크로 국면")  # 질문 대상 근거가 먼저
    assert "근거 형식을 그대로 복사함" in llm.calls[1]


def test_answer_must_mention_target():
    off = "VIX는 28.3으로 최근 1개월 최고 35.9보다 낮습니다. 국면 점수는 -1입니다."
    issues = QA.answer_issues(off, D.text() + SEMIS.text(), ["반도체"])
    assert any(i.startswith("질문 대상(반도체) 언급 없음") for i in issues)
    assert QA.answer_issues("이 화면의 자료로는 답할 수 없습니다. 대신 국면 점수를 보세요.", D.text(), ["반도체"]) == []


def test_fallback_picks_question_relevant_facts():
    """11-28 운영: 두 번 반려 뒤 대체 문장이 매크로 화면 첫 줄(국면 점수)이었음 → 질문과 가까운 반도체 비교 문장을."""
    llm = Scripted("반도체는 평균보다 9.2%p 낮습니다. 수익률은 42.0%입니다.", "반도체는 평균보다 9.2%p 낮습니다.")
    r = QA.answer("반도체 산업은 2026년 수익률 비교시 10년 평균보다 높았어?", D, llm, CFG, extra=[SEMIS])
    assert r["mode"] == "fallback" and r["routed"] == ["group:semis"]
    assert "2026년(1~11월, 진행 중) 그룹 수익률 +0.6%" in r["text"] and "국면 점수 -1" not in r["text"]
    assert any("근거에 없는 숫자" in i for i in r["issues"])


def test_page_evidence_trimmed_when_target_routed():
    long_page = Digest("macro", "macro", "II. 매크로 국면", "2026-11-25", [f"사실 {i}" for i in range(20)])
    ev = QA.evidence(long_page, "반도체는?", extra=[SEMIS])
    assert "사실 5" in ev and "사실 6" not in ev and ev.index("반도체") < ev.index("II. 매크로")
