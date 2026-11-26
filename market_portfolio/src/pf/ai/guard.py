"""AI 답변 검증과 질문 범위 제한 (PLAN.md §8.1, §12.2 규칙 2·5·6).

LLM을 '틀릴 수 있는 부품'으로 보고 출력 쪽을 코드로 막는다.
  - 답변의 숫자·날짜가 근거(digest)에 없으면 버린다 (계산·창작 금지)
  - 지시형·단정형 금지어가 있으면 버린다
  - 너무 짧거나 길면 버린다
  - 매수·매도·비중·목표가 질문은 LLM을 부르기 전에 거절한다 (거절률 100% 관문은 규칙으로 지킨다)

알려진 한계: 숫자는 절댓값으로 대조한다("10.7% 하락" 같은 자연스러운 표현을 허용하기 위해).
부호·방향 단어가 뒤집힌 오류는 골든 세트 평가에서 잡는다.
"""

from __future__ import annotations

import re

from pf.synth.rules import BANNED

# 금지어: F19 목록 + 해설에서 자주 새는 권유 표현
EXTRA_BANNED = ("추천합니다", "권합니다", "권장합니다", "목표가", "매수 기회", "매도 시점", "들어가세요", "담으세요")

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
NUM_RE = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?")
TOL = 0.051  # 반올림 차이 허용 (예: 근거 12.34 → 답변 12.3)

MIN_CHARS, MAX_CHARS = 40, 900

# 범위 밖 질문 (투자 행동 권유 요청). 사이트는 지표 뜻·화면 읽는 법·수치 요약만 답한다.
OUT_OF_SCOPE = re.compile(
    r"(사야|살까|사도\s*돼|사도\s*될|팔아야|팔까|팔아도|매수|매도|손절|익절|비중|목표\s*가|목표주가|"
    r"얼마까지\s*(오|떨어)|들어가도|진입|추천\s*(종목|해)|몰빵|레버리지|포트폴리오\s*(짜|구성))"
)
REFUSAL = ("이 해설은 매수·매도·비중·목표가 같은 투자 판단을 다루지 않습니다. "
           "대신 화면의 하락 확률·90% 구간·국면 점수가 무엇을 뜻하는지, 지금 수치가 어떤지는 설명할 수 있습니다.")


def _numbers(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in NUM_RE.findall(DATE_RE.sub(" ", text))]


def allowed(evidence: str) -> tuple[set[float], set[str]]:
    """근거 문장에서 허용 숫자와 날짜. 날짜의 연·월·일 숫자도 허용(‘2026년 12월 9일’ 표기)."""
    dates = set(DATE_RE.findall(evidence))
    nums = set(_numbers(evidence))
    for d in dates:
        y, m, dd = d.split("-")
        nums |= {float(y), float(int(m)), float(int(dd))}
    return nums, dates


def check(answer: str, evidence: str, loss: list[str] | None = None) -> list[str]:
    """문제 목록. 비어 있으면 통과.

    loss: 손실 쪽 숫자(90% 하단·CVaR 등 근거 표기 그대로). 주어지면 답변에 하나 이상 있어야 한다
    (사이트 원칙: 확률·기대값과 손실 쪽 숫자를 함께 — 프롬프트만으로는 지켜지지 않음, 11-26 실측).
    """
    issues = []
    text = answer.strip()
    if len(text) < MIN_CHARS:
        issues.append("너무 짧음")
    if len(text) > MAX_CHARS:
        issues.append("너무 김")
    words = [w for w in BANNED + EXTRA_BANNED if w in text]
    if words:
        issues.append("금지어: " + ", ".join(words))
    nums, dates = allowed(evidence)
    bad_dates = sorted(set(DATE_RE.findall(text)) - dates)
    if bad_dates:
        issues.append("근거에 없는 날짜: " + ", ".join(bad_dates))
    bad = [n for n in _numbers(text) if not any(abs(n - a) <= TOL for a in nums)]
    if bad:
        issues.append("근거에 없는 숫자: " + ", ".join(f"{n:g}" for n in dict.fromkeys(bad)))
    if loss:
        want = {abs(v) for l in loss for v in _numbers(l)}
        if not any(any(abs(n - w) <= TOL for w in want) for n in _numbers(text)):
            issues.append("손실 쪽 숫자 없음 (90% 구간 하단: " + ", ".join(loss[:3]) + ")")
    return issues


def out_of_scope(question: str) -> bool:
    return bool(OUT_OF_SCOPE.search(question.replace(" ", " ")))
