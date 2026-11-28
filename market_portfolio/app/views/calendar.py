"""III. 실적 캘린더 — 이번 달 누가, 어느 그룹이 발표하나 (F11). calendar.json만 읽는다."""

from __future__ import annotations

import json

import streamlit as st

from pf.publish.group import CALENDAR_PATH


@st.cache_data(ttl=300)
def calendar():
    return json.loads(CALENDAR_PATH.read_text(encoding="utf-8")) if CALENDAR_PATH.exists() else None


def pct(v):
    if v is None:
        return "—"
    x = round(v * 100, 1)
    return "0.0%" if x == 0 else f"{x:+.1f}%"


def goto(page: str, **state) -> None:
    for k, v in state.items():
        st.session_state[k] = v
    st.session_state["_goto"] = page


st.title("III. 실적 캘린더")
st.caption("이번 달 누가, 어느 그룹이 발표하나 — 관심 그룹별 발표 예정 종목과 그룹의 과거 실적 시즌 반응")

d = calendar()
if d is None:
    st.warning("캘린더 계산 결과가 아직 없습니다. 다음 매일 배치(07:15 KST) 뒤에 표시됩니다.")
    st.stop()

if "cal_period" not in st.session_state:
    st.session_state["cal_period"] = "4주"
period = st.segmented_control("기간", ["2주", "4주", "12주"], key="cal_period") or "4주"
limit = {"2주": 14, "4주": 28, "12주": 84}[period]

groups = []
for g in d["groups"]:
    evs = [e for e in g["events"] if e["days"] <= limit]
    groups.append({**g, "events": evs})
active = sorted([g for g in groups if g["events"]], key=lambda g: g["events"][0]["days"])
quiet = [g["name"] for g in groups if not g["events"]]
n_tickers = len({e["ticker"] for g in active for e in g["events"]})
st.caption(f"기준일 {d['asof']} · {period} 안에 {len(active)}개 그룹 · {n_tickers}종목 발표 예정 (테마 그룹은 산업 그룹과 종목이 겹칠 수 있음)")

cols = st.columns(2, gap="medium")
for i, g in enumerate(active):
    with cols[i % 2].container(border=True):
        badge = " :gray-background[테마]" if g["kind"] == "theme" else ""
        st.markdown(f"**{g['name']}**{badge} · 벤치마크 {g['benchmark']}")
        c = g.get("car21") or {}
        if c:
            st.markdown(
                f"과거 실적 후 21일 초과수익 중앙값 **{pct(c['median'])}** · 90% 범위 {pct(c['p5'])} ~ {pct(c['p95'])}  \n"
                f":gray-background[참고용] 하락 비율 {c['p_down'] * 100:.0f}% · 표본 {c['n']}건"
            )
        chip_cols = st.columns(2)
        for j, e in enumerate(g["events"]):
            timing = {"AMC": "장후", "BMO": "장전"}.get(e["timing"], "")
            chip_cols[j % 2].button(
                f"{e['ticker']} · {e['date'][5:].replace('-', '/')} · D-{e['days']} {timing}",
                key=f"c_{g['id']}_{e['ticker']}",
                help=f"다음 날 P(하락) {e['p_down'] * 100:.0f}% · 기대값 {pct(e['mean'])} · 90% {pct(e['p5'])} ~ {pct(e['p95'])}",
                on_click=goto, args=("views/ticker.py",), kwargs={"ticker": e["ticker"]},
                width="stretch",
            )
        st.button("그룹 상세 →", key=f"cg_{g['id']}", on_click=goto, args=("views/group.py",), kwargs={"group": g["id"]})

if quiet:
    st.caption(f"{period} 안에 발표 없음: " + ", ".join(quiet))

if (page := st.session_state.pop("_goto", None)):
    st.switch_page(page)
