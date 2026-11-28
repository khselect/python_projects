"""비교 문장 (코드 계산) — AI가 평균·순위를 만들지 않고 옮기기만 하도록."""

from pf.ai import guard
from pf.ai.compare import group_year_facts, macro_history_facts

HM = {
    "years": list(range(2014, 2027)),
    "values": [[0.01] * 12 for _ in range(12)] + [[0.02] * 11 + [None]],   # 과거 매달 +1%, 올해 1~11월 +2%
    "annual": [0.1268] * 12 + [0.2434], "bench_annual": [0.10] * 6 + [0.20] * 6 + [0.05],
    "partial_last_year": True,
}


def test_group_same_period_comparison_and_rank():
    f = group_year_facts(HM, "2026-11-25")
    assert f[0].startswith("2026년(1~11월, 진행 중·11월은 기준일까지) 그룹 수익률 +24.3%")
    assert "같은 기간 평균 +11.6%보다 12.7%p 높음" in f[0]  # 차이도 미리 계산
    assert "11년 중 1위" in f[1]
    assert any("11월(기준일까지) 그룹 수익률 +2.0%" in x and "1.0%p 높음" in x for x in f)
    assert any("벤치마크보다 수익률이 높았던 해 4/10년" in x for x in f)


def test_comparison_numbers_pass_guard_when_copied():
    """모델이 비교 문장을 그대로 옮기면 검증을 통과해야 한다 (추론 없이 답 가능)."""
    f = group_year_facts(HM, "2026-11-25")
    ev = "\n".join(f"- {x}" for x in f)
    ans = (f"{f[0].split(' — ')[0]}입니다. 과거 10년 같은 기간 평균 +11.6%보다 12.7%p 높고, "
           "같은 기간 순위는 11년 중 1위입니다.")
    assert guard.check(ans, ev) == []


def test_macro_history_facts():
    m = {"score": -1, "asof": "2026-11-25", "regime": "중립·전환", "regime_since": "2026-11-20",
         "thresholds": {"expansion": 4, "riskoff": -4},
         "history": {"score": [-5, -3, -1, 0, 2, 4, -1, -2, 1, 3], "stress": [True] + [False] * 9},
         "indicators": [{"key": "vix", "values": {"level": 28.3, "pct_1y": 0.91, "max_1y": 35.9}}]}
    f = macro_history_facts(m)
    assert "지금(-1)보다 낮았던 주 3개, 같았던 주 2개" in f[0] and "최저 -5, 최고 +4" in f[0]
    assert f[1] == "최근 2년 10주 중 위험회피 1주, 확장 1주, 급변 규칙 발동 1주"
    assert "5일째" in f[2] and "91%의 날보다 높은 수준 (1년 최고 35.9)" in f[3]


def test_short_history_returns_nothing():
    assert group_year_facts({"years": [2025, 2026], "values": [[0.01] * 12] * 2}, "2026-11-25") == []
    assert macro_history_facts({"score": 0, "history": {"score": [0, 1]}}) == []
