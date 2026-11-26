"""⑤ 종합·질문 — 모든 화면 오른쪽에 고정되는 패널 (F19 종합 판단, F20 AI 해설 자리).

보고 있는 화면의 맥락(그룹·종목)을 따라간다.
  ④ 종목 상세 : 선택한 종목 + 그 종목의 산업 그룹
  그 외 화면  : 사이드바 관심 그룹 (+ ④에서 마지막으로 본 종목이 같은 그룹이면 함께)
"""

from __future__ import annotations

import json

import streamlit as st

from common import coverage
from pf.macro.publish import MACRO_PATH
from pf.publish.group import load_group
from pf.publish.ticker import load_published
from pf.synth.rules import synthesize

BADGE_COLOR = {"agree_pos": "blue", "agree_neg": "red", "conflict": "orange", "partial": "gray", "neutral": "gray", "none": "gray"}
STICKY_CSS = """
<style>
/* 오른쪽 ⑤ 패널: 스크롤해도 화면에 고정 (넓은 화면에서만, 좁으면 아래로 쌓임).
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
def _ticker(t: str):
    return load_published(t)


def _context(page_path: str) -> tuple[str, str | None]:
    cov = coverage()
    gid = st.session_state.get("group") or cov.defaults.get("groups", ["semis"])[0]
    t = st.session_state.get("ticker")
    if page_path == "ticker":
        t = t if t in cov.tickers else "AVGO"  # ④ 첫 진입 기본값과 같게
        own = next((g.id for g in cov.industry if t in g.members), gid)
        return own, t
    members = cov.group(gid).members
    return gid, (t if t in members else None)


def render(page_path: str) -> None:
    st.html(STICKY_CSS)
    st.markdown('<div class="synth-anchor"></div>', unsafe_allow_html=True)
    st.subheader("⑤ 종합·질문")
    gid, t = _context(page_path)
    gname = coverage().group(gid).name
    st.caption(f"보는 중: {gname}" + (f" · {t}" if t else ""))

    v = synthesize(_macro(), _group(gid), _ticker(t) if t else None)
    st.markdown(f"**:{BADGE_COLOR[v.code]}-background[{v.title}]**")
    st.caption(v.text)
    for layer in v.layers:
        ref = " :gray-background[참고용]" if layer.reference_only else ""
        st.markdown(f"**{layer.name}** · {layer.label}{ref}")
        st.caption(layer.basis)
    st.caption("상위 층(매크로 → 그룹 → 종목)을 우선하고 점수를 평균내지 않습니다. 과거 통계 기반 참고 정보입니다.")

    st.divider()
    st.markdown("**AI 해설**")
    st.caption("v1 예정 — 맥미니 로컬 sLLM(Ollama)이 사이트 수치와 용어 가이드만 근거로 답합니다.")
    st.chat_input("질문 (v1에서 사용 가능)", disabled=True, key="ai_q")
