"""③ 그룹 상세 — 이 그룹은 실적 시즌에 어떻게 움직였나 (F12·F13). 게시 JSON만 읽는다."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from charts import car_chart, month_heatmap
from common import coverage, tip
from pf.publish.group import load_group


def pct(v, signed=True):
    if v is None:
        return "—"
    x = round(v * 100, 1)
    if x == 0:
        return "0.0%"
    return f"{x:+.1f}%" if signed else f"{x:.1f}%"


@st.cache_data(ttl=300)
def group_json(gid: str):
    return load_group(gid)


def goto_ticker(t: str) -> None:
    st.session_state["ticker"] = t
    st.session_state["_goto"] = "views/ticker.py"


cov = coverage()
gid = st.session_state.get("group", cov.defaults.get("groups", ["semis"])[0])
d = group_json(gid)
g = cov.group(gid)
st.title(f"③ 그룹 상세 — {g.name}")
if d is None:
    st.warning("그룹 계산 결과가 아직 없습니다. 다음 매일 배치(07:15 KST) 뒤에 표시됩니다.")
    st.code("docker compose exec market-jobs python -m pf.jobs.run daily", language="bash")
    st.stop()

kind = "테마 그룹" if d["group"]["kind"] == "theme" else "산업 그룹"
st.caption(
    f"{kind} · 벤치마크 {d['group']['benchmark']} · 구성 {', '.join(d['group']['members'])} · "
    f"기준일 {d['asof']} · {d['note']}"
)

# ── 실적 시즌 반응 (CAR) ─────────────────────────────────
car = d["car"]
st.subheader("실적일 기준 누적 초과수익률", help=tip("car"))
if car.get("n_events", 0) == 0:
    st.info("계산 가능한 실적 이벤트가 없습니다.")
else:
    c21 = car["car21"]
    k = st.columns(4)
    k[0].metric("21일 초과수익 중앙값", pct(c21["median"]))
    k[1].metric("90% 범위 하단", pct(c21["p5"]))
    k[2].metric("90% 범위 상단", pct(c21["p95"]))
    k[3].metric("21일 하락 비율", f"{c21['p_down'] * 100:.0f}%")
    st.caption(
        f":gray-background[참고용] 이벤트 {car['n_events']}건 ({car['first']} ~ {car['last']}) · "
        f"반응일(0)부터 21거래일 · 벤치마크 {d['group']['benchmark']} 대비 β 조정 초과수익 · 과거 통계"
    )
    st.plotly_chart(car_chart(car), width="stretch", config={"displayModeBar": False})

# ── 다가오는 발표 ─────────────────────────────────────────
st.subheader("다가오는 발표 (12주)")
ups = d["upcoming"]
if not ups:
    st.caption("12주 안에 발표 예정인 구성 종목이 없습니다.")
else:
    st.dataframe(pd.DataFrame([{
        "종목": e["ticker"], "발표일": e["date"], "D-day": f"D-{e['days']}",
        "시점": {"AMC": "장후", "BMO": "장전"}.get(e["timing"], "미상"),
        "P(하락)": f"{e['p_down'] * 100:.0f}%", "다음 날 기대값": pct(e["mean"]),
        "90% 구간": f"{pct(e['p5'])} ~ {pct(e['p95'])}", "표본": e["n_events"],
    } for e in ups]), hide_index=True, width="stretch")
    cols = st.columns(min(len(ups), 5))
    for i, e in enumerate(ups[:5]):
        cols[i].button(f"{e['ticker']} 상세 →", key=f"g_{e['ticker']}", on_click=goto_ticker, args=(e["ticker"],))

# ── 연도×월 수익률 ────────────────────────────────────────
h = d["heatmap"]
st.subheader("연도×월 수익률 (동일가중)")
HEAT_MODES = {"그룹 수익률": "group", f"{d['group']['benchmark']} 대비 차이": "excess", "월중 최대 낙폭": "mdd"}
has_extra = "bench_values" in h and "mdd" in h  # 이전 배치 JSON에는 없음 → 다음 배치 후 표시
if has_extra:
    if st.session_state.get("heat_mode") not in HEAT_MODES:
        st.session_state["heat_mode"] = "그룹 수익률"
    sel = st.segmented_control("칸에 표시할 값", list(HEAT_MODES), key="heat_mode") or "그룹 수익률"
    mode = HEAT_MODES[sel]
else:
    mode = "group"
st.plotly_chart(
    month_heatmap(h["years"], h["values"], h.get("bench_values"), h.get("mdd"), mode, d["group"]["benchmark"]),
    width="stretch", config={"displayModeBar": False},
)
st.caption({
    "group": "칸 = 그 달 그룹 수익률(전달 말 → 이번 달 말). 마우스를 올리면 벤치마크·차이·월중 최대 낙폭도 보입니다.",
    "excess": f"칸 = 그룹 − {d['group']['benchmark']} (%p). 파랑 = 벤치마크보다 강함, 빨강 = 약함.",
    "mdd": "칸 = 월중 최대 낙폭: 그 달 안에서 고점 대비 가장 많이 빠진 정도. 월말 수익률이 작아도 월중에 크게 흔들렸는지 확인.",
}[mode] + ("" if has_extra else " (벤치마크·월중 낙폭은 다음 매일 배치 뒤 표시)"))
annual = pd.DataFrame({
    "연도": [str(y) + ("(진행 중)" if h["partial_last_year"] and y == h["years"][-1] else "") for y in h["years"]],
    "그룹": [pct(v) for v in h["annual"]],
    d["group"]["benchmark"]: [pct(v) for v in h["bench_annual"]],
    "차이": [pct(None if a is None or b is None else a - b) for a, b in zip(h["annual"], h["bench_annual"])],
}).iloc[::-1]
st.dataframe(annual, hide_index=True, width="stretch")
st.caption("동일가중 = 매달 초 구성 종목에 같은 비중 (구성 종목 월수익률의 평균). 시가총액가중은 v1에서 추가.")

if st.session_state.pop("_goto", None):
    st.switch_page("views/ticker.py")
