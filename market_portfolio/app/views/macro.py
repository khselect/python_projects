import streamlit as st

from common import tip

st.title("① 매크로 국면")
st.caption("큰 자금은 어디로 움직이나 — F16·F17 (MVP 3단계, 12월 중순 예정)")

st.info("이 화면은 준비 중입니다. 지금 볼 수 있는 계산 결과는 ④ 종목 상세입니다.", icon="🛠️")
st.page_link("views/ticker.py", label="④ 종목 상세 — 실적 반응 분포 보기 (AVGO 12/09 실적)", icon="➡️")

st.divider()
c1, c2 = st.columns([1, 3])
c1.metric("국면 점수", "—", help=tip("regime_score"))
c2.caption("6개 지표(유동성·원자재·시장 폭·신용·금리곡선·달러) 체크리스트가 여기에 표시됩니다.")
