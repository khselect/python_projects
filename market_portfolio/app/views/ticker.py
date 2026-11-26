import streamlit as st

from common import coverage, tip

cov = coverage()
st.title("④ 종목 상세")
st.caption("다음 실적에 어떻게 반응할까 — F3~F7 (MVP 3단계, AVGO 우선)")

main, side = st.columns([3, 1])
with main:
    ticker = st.selectbox("종목", cov.tickers, index=cov.tickers.index("AVGO"))
    cols = st.columns(4)
    cols[0].metric("P(상승)", "—")
    cols[1].metric("P(하락)", "—", help=tip("p_down"))
    cols[2].metric("기대값", "—")
    cols[3].metric("90% 구간", "—", help=tip("interval90"))
with side:
    st.subheader("비교 조회")
    st.caption("준비 중")
