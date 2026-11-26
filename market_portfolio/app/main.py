"""market.sielain.com 진입점. 화면 순서는 탑다운: ① 매크로 → ② 캘린더 → ③ 그룹 → ④ 종목.

세로 3분할: 왼쪽 사이드바(메뉴·관심 그룹) | 가운데 화면 | 오른쪽 ⑤ 종합·질문 패널(항상 표시, 스크롤 고정).
패널은 화면보다 먼저 그린다(화면의 st.stop()에 영향받지 않게). 위젯 선택값은 다시 실행되기 전에
session_state에 들어가므로, 화면에서 고른 종목·그룹이 패널에 그대로 반영된다.
"""

from __future__ import annotations

import streamlit as st

from common import footer, sidebar
from panel import render as render_panel

st.set_page_config(page_title="Portfolio · 실적 반응", page_icon="📈", layout="wide")

pages = [
    st.Page("views/macro.py", title="① 매크로 국면", url_path="macro", default=True),
    st.Page("views/calendar.py", title="② 실적 캘린더", url_path="calendar"),
    st.Page("views/group.py", title="③ 그룹 상세", url_path="group"),
    st.Page("views/ticker.py", title="④ 종목 상세", url_path="ticker"),
]

nav = st.navigation(pages)
sidebar()
center, right = st.columns([3, 1], gap="large")
with right:  # 패널을 먼저 그린다 — 화면이 자료 없음으로 st.stop()해도 패널은 남도록
    render_panel(nav.url_path)
with center:
    nav.run()
    footer()
