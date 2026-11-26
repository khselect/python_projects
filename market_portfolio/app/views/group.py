import streamlit as st

from common import coverage, tip

g = coverage().group(st.session_state.get("group", "semis"))
st.title(f"③ 그룹 상세 — {g.name}")
st.caption(f"벤치마크 {g.benchmark} · 구성 종목 {', '.join(g.members)} (현재 구성 기준)")
st.info("연도×월 히트맵(F12)과 실적일 정렬 CAR(F13)은 준비 중입니다 (MVP 4단계).", icon="🛠️")
st.page_link("views/ticker.py", label="④ 종목 상세 — 실적 반응 분포 보기", icon="➡️")
st.caption(f"CAR: {tip('car')}")
