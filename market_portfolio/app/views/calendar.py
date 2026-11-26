import streamlit as st

st.title("② 실적 캘린더")
st.caption("이번 달 누가, 어느 그룹이 발표하나 — F11 (MVP 4단계)")
st.segmented_control("기간", ["2주", "4주", "12주"], default="4주", key="cal_period")
st.info("그룹 카드와 발표 예정 칩이 여기에 표시됩니다.")
