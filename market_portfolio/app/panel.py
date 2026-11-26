"""종합 인사이트 — 모든 화면 오른쪽에 고정되는 패널 (F19 세 층 판정, F20 AI 해설).

이름 (v0.17): 판정은 AI가 아닌 규칙 계산이라 "AI 어시스턴트" 대신 "종합 인사이트".
F20 연결 뒤 AI 칸을 위로 올리거나 이름을 바꿀 수 있다.

보고 있는 화면의 맥락(그룹·종목)을 따라간다.
  ④ 종목 상세 : 선택한 종목 + 그 종목의 산업 그룹
  그 외 화면  : 사이드바 관심 그룹 (+ ④에서 마지막으로 본 종목이 같은 그룹이면 함께)
"""

from __future__ import annotations

import json

import streamlit as st

from common import coverage
from pf.ai.pregen import load_ai
from pf.macro.publish import MACRO_PATH
from pf.publish.group import load_group
from pf.publish.ticker import load_published
from pf.synth.rules import synthesize

BADGE_COLOR = {"agree_pos": "blue", "agree_neg": "red", "conflict": "orange", "partial": "gray", "neutral": "gray", "none": "gray"}
STICKY_CSS = """
<style>
/* 오른쪽 종합 인사이트 패널: 스크롤해도 화면에 고정 (넓은 화면에서만, 좁으면 아래로 쌓임).
   열을 행 높이만큼 늘이지 않도록 부모 행의 정렬을 위쪽으로 두고, 패널 열에 sticky를 준다. */
@media (min-width: 900px) {
  div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"] .synth-anchor) {
    align-items: flex-start;
  }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"][data-testid="stColumn"]:has(.synth-anchor) {
    position: sticky; top: 3.75rem; align-self: flex-start; height: auto;
    max-height: calc(100vh - 4.5rem); overflow-y: auto;
    border-left: 1px solid #e6e6e6; padding-left: 1rem;
  }
}
</style>
"""


@st.cache_data(ttl=300)
def _macro():
    return json.loads(MACRO_PATH.read_text(encoding="utf-8")) if MACRO_PATH.exists() else None


@st.cache_data(ttl=300)
def _group(gid: str):
    return load_group(gid)


@st.cache_data(ttl=300)
def _ai(kind: str, key: str):
    return load_ai(kind, key)


@st.cache_data(ttl=300)
def _ticker(t: str):
    return load_published(t)


def _context(page_path: str) -> tuple[str, str | None]:
    cov = coverage()
    gid = st.session_state.get("group") or cov.defaults.get("groups", ["semis"])[0]
    # ④의 선택 위젯 키("ticker")는 다른 화면으로 가면 Streamlit이 지운다 → 마지막으로 본 종목을 따로 쓴다
    t = st.session_state.get("ticker") or st.session_state.get("last_ticker")
    if page_path == "ticker":
        t = t if t in cov.tickers else "AVGO"  # ④ 첫 진입 기본값과 같게
        own = next((g.id for g in cov.industry if t in g.members), gid)
        return own, t
    members = cov.group(gid).members
    return gid, (t if t in members else None)


def render(page_path: str) -> None:
    st.html(STICKY_CSS)
    st.markdown('<div class="synth-anchor"></div>', unsafe_allow_html=True)
    st.markdown("#### 종합 인사이트")
    gid, t = _context(page_path)
    gname = coverage().group(gid).name
    st.caption(f"보는 중: {gname}" + (f" · {t}" if t else ""))

    v = synthesize(_macro(), _group(gid), _ticker(t) if t else None)
    st.markdown("**세 층 판정**", help="매크로 → 그룹 → 종목. 규칙 기반 계산(AI 미사용). 상위 층을 우선하고 점수를 평균내지 않습니다.")
    st.markdown(f"**:{BADGE_COLOR[v.code]}-background[{v.title}]**")
    st.caption(v.text)
    for layer in v.layers:
        ref = " :gray-background[참고용]" if layer.reference_only else ""
        st.markdown(f"**{layer.name}** · {layer.label}{ref}")
        st.caption(layer.basis)
    st.caption("상위 층(매크로 → 그룹 → 종목)을 우선하고 점수를 평균내지 않습니다. 과거 통계 기반 참고 정보입니다.")

    st.divider()
    _ai_section(page_path, gid, t)


def _md(s: str) -> str:
    """마크다운 오해석 방지: '~'(취소선), '$'(수식)."""
    return s.replace("~", "\\~").replace("$", "\\$")


def _ai_section(page_path: str, gid: str, t: str | None) -> None:
    """F20 1단계: 매일 배치가 미리 만든 해설을 읽기만 한다 (페이지 조회당 LLM 호출 0)."""
    if page_path == "macro":
        d = _ai("macro", "macro")
    else:
        d = (_ai("ticker", t) if t else None) or _ai("group", gid)
    st.markdown("**AI 해설**", help="맥미니 로컬 sLLM(Ollama)이 매일 배치에서 이 사이트의 수치와 용어 가이드만 근거로 "
                "미리 쓴 해설입니다. 답변 속 숫자·날짜는 근거와 코드로 대조하고, 맞지 않으면 버리고 근거 요약(템플릿)을 보여줍니다.")
    if not d:
        st.caption("오늘 해설이 아직 없습니다. 다음 배치(매일 07:15) 뒤에 표시됩니다.")
    else:
        if d["mode"] == "ai":
            st.caption(f"대상: {d['title']} · {d['model']} · 기준일 {d['asof']}")
        else:
            st.caption(f"대상: {d['title']} · :gray-background[근거 요약] AI 해설을 쓰지 못해 근거 앞부분을 보여줍니다")
        st.markdown(_md(d["text"]))
        with st.expander("근거 보기"):
            st.caption(" · ".join(d.get("sources", [])))
            st.markdown("\n".join(f"- {_md(f)}" for f in d["facts"]))
            if d.get("reason"):
                st.caption(f"템플릿 사유: {d['reason']}")
        st.caption("AI가 쓴 문장은 틀릴 수 있습니다. 숫자는 위 판정과 각 화면을 기준으로 보세요. 투자 권유가 아닙니다.")
    st.chat_input("자유 질문 (다음 단계에서 사용 가능)", disabled=True, key="ai_q")
