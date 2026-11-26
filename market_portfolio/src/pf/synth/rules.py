"""F19 종합 판단 — 매크로 → 그룹 → 종목 세 층 (PLAN.md §7.6).

상위 층이 하위 층보다 우선한다. 점수를 평균내지 않는다(평균은 충돌을 숨긴다).
출력 문구는 서술형 고정 템플릿만 쓴다 — 계산하지 않은 과거 성과를 주장하지 않는다(F17 자산군 가이드 전),
LLM 미사용, 지시형("사라·팔라·늘려라·줄여라·헤지하라")·
단정형("반드시·확실히·보장") 표현 금지 (§12.2 규칙 2·5).

| 층 | 입력 | +1 | 0 | −1 |
|---|---|---|---|---|
| 1 매크로 | 국면 점수 | ≥ +3 | 그 사이 | ≤ −3 |
| 2 그룹 | 과거 실적 후 21일 초과수익 중앙값 | ≥ +0.5% | ±0.5% 이내 | ≤ −0.5% |
| 3 종목 | 다음 날 P(하락)·P(상승)·90% 하단 | P(상승) ≥ 60% 이고 하단 > −15% | 그 외 | P(하락) ≥ 60% 또는 하단 ≤ −15% |

구현 메모 (v0.16): §7.6은 그룹 층에서 "참고용이면 0"이지만, 보정 관문(F10)이 v2라 지금은 모든 그룹이
참고용이다. 그대로면 그룹 층이 항상 0이 되므로 ±0.5% 중립 구간을 두고 부호를 쓰되 "참고용"을 함께 표시한다.
종목 층의 +1 조건은 §7.6에 없어 −1 조건과 대칭으로 정했다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GROUP_BAND = 0.005
P_LEVEL = 0.60
TAIL = -0.15

BANNED = ("사라", "팔라", "매수하", "매도하", "늘려라", "줄여라", "헤지하라", "반드시", "확실히", "보장")
SIGN_LABEL = {1: "▲ 우호", 0: "● 중립", -1: "▼ 비우호", None: "— 자료 없음"}


@dataclass
class Layer:
    key: str
    name: str
    value: int | None
    basis: str
    reference_only: bool = False

    @property
    def label(self) -> str:
        return SIGN_LABEL[self.value]


@dataclass
class Verdict:
    code: str  # agree_pos | agree_neg | conflict | neutral | partial | none
    title: str
    text: str
    layers: list[Layer] = field(default_factory=list)


def _pct(v: float) -> str:
    x = round(v * 100, 1)
    return "0.0%" if x == 0 else f"{x:+.1f}%"


def macro_layer(macro: dict | None, hi: int = 3, lo: int = -3) -> Layer:
    if not macro:
        return Layer("macro", "매크로", None, "매크로 계산 결과 없음")
    s = macro["score"]
    v = 1 if s >= hi else (-1 if s <= lo else 0)
    return Layer("macro", "매크로", v, f"국면 점수 {s:+d} · {macro['regime']} ({macro['regime_since']}부터)")


def group_layer(group: dict | None) -> Layer:
    if not group or not group.get("car", {}).get("car21"):
        return Layer("group", "그룹", None, "그룹 계산 결과 없음")
    c = group["car"]["car21"]
    m = c["median"]
    v = 1 if m >= GROUP_BAND else (-1 if m <= -GROUP_BAND else 0)
    basis = (f"{group['group']['name']} 과거 실적 후 21일 초과수익 중앙값 {_pct(m)} "
             f"(90% {_pct(c['p5'])} ~ {_pct(c['p95'])}, 표본 {c['n']}건)")
    return Layer("group", "그룹", v, basis, reference_only=True)


def ticker_layer(ticker: dict | None) -> Layer:
    if not ticker:
        return Layer("ticker", "종목", None, "종목 미선택 — ④ 종목 상세에서 고르면 반영")
    h = ticker["sim"]["horizons"]["1"]
    p_down, p_up, p5 = h["p_down"], h["p_up"], h["pcts"]["5"]
    if p_down >= P_LEVEL or p5 <= TAIL:
        v = -1
    elif p_up >= P_LEVEL and p5 > TAIL:
        v = 1
    else:
        v = 0
    ev = ticker.get("next_event") or {}
    when = f"다음 실적 {ev['date']} · " if ev else ""
    basis = f"{ticker['ticker']} {when}다음 날 P(하락) {p_down * 100:.0f}% · 90% 하단 {_pct(p5)}"
    return Layer("ticker", "종목", v, basis, reference_only=ticker.get("gate", {}).get("status") == "참고용")


def synthesize(macro: dict | None, group: dict | None, ticker: dict | None) -> Verdict:
    layers = [macro_layer(macro), group_layer(group), ticker_layer(ticker)]
    vals = [l.value for l in layers if l.value is not None]
    nonzero = [l for l in layers if l.value not in (None, 0)]
    if not vals:
        return Verdict("none", "자료 없음", "계산 결과가 아직 없습니다.", layers)

    # 충돌: 상위 층과 하위 층의 부호가 반대
    for i, up in enumerate(nonzero):
        for low in nonzero[i + 1:]:
            if up.value != low.value:
                side = "우호" if up.value > 0 else "비우호"
                text = (f"{up.name} 층은 {side}, {low.name} 층은 반대 방향입니다. "
                        f"종합 규칙상 상위 층({up.name})을 우선해 읽습니다.")
                return Verdict("conflict", f"충돌 — {up.name} 우선", text, layers)

    known = [l for l in layers if l.value is not None]
    if nonzero and len(nonzero) == len(known):
        if nonzero[0].value > 0:
            return Verdict("agree_pos", "일치 — 위험자산 우호",
                           "자료가 있는 층이 모두 우호 쪽입니다.", layers)
        return Verdict("agree_neg", "일치 — 위험자산 비우호",
                       "자료가 있는 층이 모두 비우호 쪽입니다. 손실 쪽 숫자(90% 하단)를 함께 확인하세요.", layers)
    if nonzero:
        top = nonzero[0]
        side = "우호" if top.value > 0 else "비우호"
        names = ", ".join(l.name for l in known if l.value == 0)
        return Verdict("partial", f"부분 일치 — {side} 쪽",
                       f"{', '.join(l.name for l in nonzero)} 층은 {side}, {names} 층은 중립입니다.", layers)
    return Verdict("neutral", "중립", "세 층 모두 뚜렷한 방향이 없습니다.", layers)


def check_wording(text: str) -> list[str]:
    """금지어 검사 (§12.2 규칙 2·5). 걸린 단어 목록."""
    return [w for w in BANNED if w in text]
