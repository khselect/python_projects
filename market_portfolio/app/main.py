"""market.sielain.com 진입점. 화면 순서는 탑다운: ① 매크로 → ② 캘린더 → ③ 그룹 → ④ 종목 → ⑤ 종합·질문."""

from __future__ import annotations

import streamlit as st

from common import footer, sidebar

st.set_page_config(page_title="Portfolio · 실적 반응", page_icon="📈", layout="wide")

pages = [
    st.Page("views/macro.py", title="① 매크로 국면", url_path="macro", default=True),
    st.Page("views/calendar.py", title="② 실적 캘린더", url_path="calendar"),
    st.Page("views/group.py", title="③ 그룹 상세", url_path="group"),
    st.Page("views/ticker.py", title="④ 종목 상세", url_path="ticker"),
    st.Page("views/synthesis.py", title="⑤ 종합·질문", url_path="synthesis"),
]

nav = st.navigation(pages)
sidebar()
nav.run()
footer()
