"""F20 1단계: 근거(digest) → LLM → 검증(guard) → 템플릿 대체."""

import json

import pytest

from pf.ai import guard
from pf.ai.client import FakeLLM, LLMError, OllamaClient, Reply
from pf.ai.digest import Digest, pct
from pf.ai.pregen import generate_one, template_text

EV = ("[근거]\n- PG 다음 실적 2026-12-04 AMC\n"
      "- 다음 날: 상승 확률 67%, 하락 확률 33%, 기대값 +1.9%, 90% 구간 -7.3% ~ +11.2%, 표본 57건")
GOOD = "PG는 2026-12-04 실적 뒤 다음 날 상승 확률이 67%, 하락 확률이 33%입니다. 90% 구간 하단은 -7.3%로 손실 쪽도 함께 보아야 합니다."


def test_pct_format_matches_screen():
    assert pct(0.0123) == "+1.2%" and pct(-0.0734) == "-7.3%" and pct(0.0) == "0.0%"


def test_guard_passes_grounded_answer():
    assert guard.check(GOOD, EV) == []
    assert guard.check("PG의 실적일은 2026년 12월 4일이며 하락 확률은 33%, 90% 구간 하단은 7.3% 하락입니다.", EV) == []


@pytest.mark.parametrize("bad, expect", [
    (GOOD.replace("67%", "70%"), "근거에 없는 숫자"),
    (GOOD.replace("2026-12-04", "2026-12-05"), "근거에 없는 날짜"),
    (GOOD + " 반드시 오를 것입니다.", "금지어"),
    (GOOD + " 지금이 매수 기회입니다.", "금지어"),
    ("짧음", "너무 짧음"),
    (GOOD * 20, "너무 김"),
], ids=["number", "date", "banned1", "banned2", "short", "long"])
def test_guard_rejects(bad, expect):
    assert any(i.startswith(expect) for i in guard.check(bad, EV))


@pytest.mark.parametrize("q", ["AVGO 지금 사도 될까?", "비중을 줄여야 할까", "목표가 알려줘", "언제 매도해?", "손절 라인은?"])
def test_out_of_scope_questions_refused(q):
    assert guard.out_of_scope(q)


@pytest.mark.parametrize("q", ["국면 점수가 뭐야?", "90% 구간 하단은 무슨 뜻이야?", "반도체 그룹 CAR 읽는 법"])
def test_in_scope_questions_allowed(q):
    assert not guard.out_of_scope(q)


class Scripted:
    """정해진 답을 차례로 돌려주는 LLM (재시도 검증용)."""

    name, model = "scripted", "scripted"

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def available(self):
        return True, "ok"

    def chat(self, system, user, **kw):
        self.calls.append(user)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return Reply(a, self.model, 1.0, 100)

    def unload(self):
        pass


D = Digest("ticker", "PG", "④ 종목 상세 — PG", "2026-11-25",
           ["PG 다음 실적 2026-12-04 AMC", "다음 날: 상승 확률 67%, 하락 확률 33%, 기대값 +1.9%, 90% 구간 -7.3% ~ +11.2%, 표본 57건"])
CFG = {"num_predict": 400, "temperature": 0.2}


def test_retry_once_with_feedback_then_accept():
    llm = Scripted(GOOD.replace("67%", "70%"), GOOD)
    r = generate_one(llm, D, CFG)
    assert r["mode"] == "ai" and r["text"] == GOOD and len(r["attempts"]) == 2
    assert "근거에 없는 숫자: 70" in llm.calls[1]  # 반려 사유를 알려주고 다시 쓰게 한다


def test_falls_back_to_template_after_two_failures():
    r = generate_one(Scripted(GOOD + " 반드시", GOOD + " 확실히"), D, CFG)
    assert r["mode"] == "template" and r["text"] == template_text(D) and "금지어" in r["reason"]
    assert guard.check(r["text"], D.text()) == []  # 템플릿도 검증을 통과한다


def test_connection_error_no_retry():
    llm = Scripted(LLMError("Ollama 연결 실패: refused"), GOOD)
    r = generate_one(llm, D, CFG)
    assert r["mode"] == "template" and len(llm.calls) == 1 and "연결 실패" in r["reason"]


def test_fake_llm_always_grounded():
    r = FakeLLM().chat("", D.text())
    assert guard.check(r.text, D.text()) == []


def test_unreachable_ollama_reports_reason():
    ok, why = OllamaClient("gemma3:12b", host="http://127.0.0.1:9").available()
    assert not ok and "연결 실패" in why


@pytest.fixture(scope="module")
def tmp_data_ai(tmp_path_factory):
    """오프라인 매일 배치를 한 번 돌린 데이터 (모듈 공유, 경로는 test_daily와 같은 방식으로 교체)."""
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("ai")
    import pf.ai.pregen as AP
    import pf.data.fundamentals as F
    import pf.macro.evaluate as ME
    import pf.publish.overview as OV
    import pf.data.store as store
    import pf.jobs.run as run
    import pf.macro.publish as mpub
    import pf.publish.group as gpub
    import pf.publish.ticker as pub
    import pf.publish.valuation as PV
    import pf.valuation as V
    from pf.config import load_model
    from pf.data.sources import SyntheticSource

    for mod, attr, val in [
        (store, "DATA_DIR", tmp), (pub, "PUBLISH_DIR", tmp / "publish" / "ticker"), (pub, "PRED_DIR", tmp / "pred"),
        (run, "PUBLISH_DIR", tmp / "publish" / "ticker"), (run, "STATUS", tmp / "publish" / "status.json"),
        (mpub, "MACRO_PATH", tmp / "publish" / "macro.json"), (gpub, "GROUP_DIR", tmp / "publish" / "group"),
        (gpub, "CALENDAR_PATH", tmp / "publish" / "calendar.json"), (F, "DATA_DIR", tmp), (V, "DATA_DIR", tmp),
        (PV, "VAL_DIR", tmp / "publish" / "valuation"), (AP, "AI_DIR", tmp / "publish" / "ai"),
        (OV, "OVERVIEW_PATH", tmp / "publish" / "overview.json"), (ME, "EVAL_PATH", tmp / "publish" / "macro_eval.json"),
    ]:
        mp.setattr(mod, attr, val)
    cfg = load_model()
    cfg["simulation"]["n_iter"] = 20_000
    mp.setattr(pub, "load_model", lambda: cfg)
    mp.setattr(pub, "get_source", lambda: SyntheticSource())
    assert run.daily() == 0
    yield tmp
    mp.undo()


def test_pregenerate_writes_and_reuses(tmp_data_ai):
    import shutil

    import pf.ai.pregen as AP

    shutil.rmtree(AP.AI_DIR, ignore_errors=True)  # 매일 배치가 이미 만든 결과를 지우고 처음부터
    s1 = AP.pregenerate(FakeLLM())
    assert s1["n"] >= 12 and s1["ai"] == s1["n"] and s1["template"] == 0
    files = sorted(p.name for p in AP.AI_DIR.glob("*.json"))
    assert "macro_macro.json" in files and "group_bigtech.json" in files
    d = json.loads((AP.AI_DIR / "group_semis.json").read_text(encoding="utf-8"))
    assert d["facts"] and d["sources"] and d["digest_hash"].endswith(f"-p{AP.PROMPT_VERSION}")
    s2 = AP.pregenerate(FakeLLM())  # 근거가 같으면 다시 만들지 않는다
    assert s2["reused"] == s2["n"] and s2["ai"] == 0


def test_pregenerate_without_ollama_fills_templates(tmp_data_ai):
    import pf.ai.pregen as AP

    s = AP.pregenerate(OllamaClient("gemma3:12b", host="http://127.0.0.1:9"))
    assert not s["ready"] and s["template"] == s["n"] and "연결 실패" in s["why"]
    d = json.loads((AP.AI_DIR / "macro_macro.json").read_text(encoding="utf-8"))
    assert d["mode"] == "template" and d["text"]


def test_digest_handles_missing_valuation_values():
    """실데이터: 합산 FCF·순이익이 0 이하면 P/FCF·P/E가 None (맥미니 첫 실행에서 발견, 11-26)."""
    from pf.ai.digest import _valuation_facts

    val = {"coverage": {"have": ["A"], "missing": []}, "forward_pe": {"values": [None]},
           "ttm": {"pe": [20.0, 25.5], "pfcf": [30.0, None], "gap": [10.0, None], "conv": [0.6, None], "n": [1, 1]}}
    f = _valuation_facts(val)
    assert f == ["후행 P/E 25.5배, P/FCF 산출 불가(합산 FCF 0 이하) (재무 확보 1종목 합산)"]
    val["ttm"]["pe"][-1] = None
    assert "P/E 산출 불가" in _valuation_facts(val)[0]


def test_one_bad_context_does_not_stop_others(tmp_data_ai, monkeypatch):
    import pf.ai.pregen as AP

    real = AP.group_digest

    def boom(grp, *a):
        if grp["group"]["id"] == "semis":
            raise TypeError("bad value")
        return real(grp, *a)

    monkeypatch.setattr(AP, "group_digest", boom)
    s = AP.pregenerate(FakeLLM())
    assert "semis" in s["digest_errors"] and s["n"] >= 11


def test_guard_requires_loss_side_number():
    """맥미니 실측(11-26): 12b가 확률·중앙값만 쓰고 90% 하단을 빠뜨림 → 코드로 강제."""
    no_loss = "PG는 2026-12-04 실적 뒤 다음 날 상승 확률이 67%, 하락 확률이 33%이며 기대값은 +1.9%입니다."
    assert any(i.startswith("손실 쪽 숫자 없음") for i in guard.check(no_loss, EV, ["-7.3%"]))
    assert guard.check(GOOD, EV, ["-7.3%"]) == []
    assert guard.check(no_loss, EV) == []  # loss 미지정(매크로 등)이면 검사 안 함


def test_retry_feedback_mentions_missing_loss():
    d = Digest(D.kind, D.key, D.title, D.asof, D.facts, loss=["-7.3%"])
    no_loss = "PG는 2026-12-04 실적 뒤 다음 날 상승 확률이 67%, 하락 확률이 33%이며 기대값은 +1.9%입니다."
    llm = Scripted(no_loss, GOOD)
    assert generate_one(llm, d, CFG)["mode"] == "ai"
    assert "손실 쪽 숫자 없음" in llm.calls[1]


def test_group_digest_separates_benchmark_and_score_format(tmp_data_ai):
    import json as _j

    import pf.macro.publish as mpub
    from pf.ai.digest import group_digest, macro_digest
    from pf.publish.group import load_group
    from pf.synth.rules import fmt_score

    d = group_digest(load_group("semis"))
    assert d.facts[0] == "반도체 그룹 구성 종목: NVDA, AVGO, AMD, MU, QCOM"
    assert "구성 종목이 아님" in d.facts[1] and d.loss
    assert template_text(d) and guard.check(template_text(d), d.text(), d.loss) == []
    m = _j.loads(mpub.MACRO_PATH.read_text(encoding="utf-8"))
    m["score"] = 0
    assert "국면 점수 0 (" in macro_digest(m).facts[0]
    assert fmt_score(0) == "0" and fmt_score(3) == "+3" and fmt_score(-2) == "-2"
