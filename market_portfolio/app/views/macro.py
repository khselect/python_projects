import streamlit as st

from common import tip

st.title("① 매크로 국면")
st.caption("큰 자금은 어디로 움직이나 — F16·F17 (MVP 2단계에서 구현)")

c1, c2 = st.columns([1, 3])
c1.metric("국면 점수", "—", help=tip("regime_score"))
c2.info("6개 지표(유동성·원자재·시장 폭·신용·금리곡선·달러) 체크리스트가 여기에 표시됩니다.")
