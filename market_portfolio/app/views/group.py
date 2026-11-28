"""IV. 그룹 상세 — 이 그룹은 실적 시즌에 어떻게 움직였나 (F12·F13). 게시 JSON만 읽는다."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from charts import car_chart, month_heatmap, valuation_chart, valuation_gap_chart
from common import coverage, tip
from pf.publish.group import load_group
from pf.publish.valuation import load_valuation


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


@st.cache_data(ttl=300)
def valuation_json(gid: str):
    return load_valuation(gid)


def goto_ticker(t: str) -> None:
    st.session_state["ticker"] = t
    st.session_state["_goto"] = "views/ticker.py"


cov = coverage()
gid = st.session_state.get("group", cov.defaults.get("groups", ["semis"])[0])
d = group_json(gid)
g = cov.group(gid)
st.title(f"IV. 그룹 상세 — {g.name}")
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

# ── 밸류에이션: P/E·P/FCF와 괴리 ──────────────────────────
VALUATION_GUIDE = """
- **파란 선 P/E**와 **주황 선 P/FCF**는 둘 다 *그룹 시가총액 ÷ 최근 1년(4개 분기) 합계*입니다. P/E는 순이익으로, P/FCF는 잉여현금흐름(영업현금흐름 − 설비투자)으로 나눕니다.
- **배수가 내려가는 이유는 두 가지**입니다: 주가(시가총액)가 내리거나, 이익이 늘거나. 위 "지금 읽는 법"의 1년 변화가 둘 중 어느 쪽이었는지 나눠 보여줍니다.
- **두 선이 붙어 움직이면** 이익만큼 현금이 남는 상태입니다. **주황이 파랑 위로 벌어지면**(아래 그래프 괴리 > 0) 이익보다 남는 현금이 적다는 뜻이고, 보통 설비투자·재고·매출채권이 늘 때 나타납니다. 주황이 아래면 감가상각 등으로 현금이 이익보다 많은 상태입니다.
- **계단 모양**은 분기 실적이 분기 말 45일 뒤(발표 무렵) 한 번에 반영되기 때문입니다. 그 사이 움직임은 주가 변화입니다.
- **점선 세로선**은 재무를 확보한 종목 수가 바뀐 날입니다. 그날의 급변은 밸류에이션 변화가 아니라 그룹 구성 변화입니다.
- 그룹 배수는 **시가총액 가중**이라 큰 종목의 영향이 큽니다. 종목별 값은 아래 표에서 보세요.
- 그룹 전체 이익이나 FCF가 0 이하인 날은 배수를 비워 둡니다(음수 배수는 의미가 없어서).
"""


def status_text(r: dict) -> str:
    """종목별 상태 — 데이터 상태와 계산상 주의점 (좋다·나쁘다 판정 아님)."""
    if r.get("missing"):
        return "재무 수집 대기 (하루 20회 한도로 나눠 받는 중)"
    flags = r.get("flags") or []
    got = (r.get("fetched_at") or "")[:10]
    base = f"반영 중 · 재무 받은 날 {got}" if got else "반영 중"
    return " · ".join([base] + flags)


def valuation_reading(ins: dict | None) -> list[str]:
    """밸류에이션 해설 — 계산값을 고정 문장 틀에 넣는다 (서술형, 판정·권유 없음)."""
    if not ins:
        return []
    out = [f"후행 P/E **{ins['pe']:.1f}배** — {ins['since'][:4]}년 이후 지금보다 낮았던 날의 비율 **{ins['pe_pct'] * 100:.0f}%** "
           f"(중앙값 {ins['pe_median']:.1f}배, 10~90% 범위 {ins['pe_p10']:.0f}~{ins['pe_p90']:.0f}배)."]
    if ins.get("pe_1y") is not None:
        s = f"1년 전({ins['date_1y']}) {ins['pe_1y']:.1f}배 → 지금 {ins['pe']:.1f}배."
        m, n = ins.get("mcap_chg_1y"), ins.get("ni_chg_1y")
        if m is not None and n is not None:
            import math
            lm, ln = math.log1p(m), math.log1p(n)
            driver = "주가(시가총액)" if abs(lm) >= abs(ln) else "이익"
            s += (f" 그 사이 시가총액 {m * 100:+.0f}%, 순이익 {n * 100:+.0f}% — 배수 변화는 주로 **{driver}** 쪽에서 왔습니다.")
        else:
            s += " 그 사이 반영 종목 수가 바뀌어 주가·이익 분해는 생략합니다."
        out.append(s)
    c, c1 = ins.get("conv"), ins.get("conv_1y")
    if c is not None:
        s = f"FCF 전환율(FCF ÷ 순이익) **{c * 100:.0f}%**" + (f" (1년 전 {c1 * 100:.0f}%)" if c1 is not None else "")
        k, k1 = ins.get("capex_share"), ins.get("capex_share_1y")
        if k is not None:
            s += f", 설비투자 ÷ 영업현금흐름 {k * 100:.0f}%" + (f" (1년 전 {k1 * 100:.0f}%)" if k1 is not None else "")
        s += "."
        if c1 is not None and k is not None and k1 is not None:
            if c < c1 - 0.05 and k > k1 + 0.05:
                s += " 이익 대비 남는 현금이 줄었고 같은 기간 설비투자 비중이 커졌습니다 — 괴리가 벌어진 배경으로 읽힙니다."
            elif c > c1 + 0.05:
                s += " 이익 대비 남는 현금이 1년 전보다 늘었습니다."
        out.append(s)
    return out


st.subheader("밸류에이션 — P/E · P/FCF 괴리", help="이익(P/E)과 현금흐름(P/FCF)으로 잰 배수가 벌어지면, 이익만큼 현금이 남지 않는다는 뜻입니다 (예: 설비투자 급증).")
v = valuation_json(gid)
cv = (v or {}).get("coverage", {"have": [], "missing": list(g.members)})
if not v or not v["ttm"]["dates"]:
    st.info(f"재무제표 수집 중 — {len(cv['have'])}/{len(g.members)}종목. 무료 데이터 한도 때문에 매일 나눠 받습니다(빅테크·반도체 우선).", icon="⏳")
else:
    t = v["ttm"]
    last = lambda k: next((x for x in reversed(t[k]) if x is not None), None)  # noqa: E731
    k = st.columns(4)
    k[0].metric("P/E (후행)", f"{last('pe'):.1f}배" if last("pe") else "—")
    k[1].metric("P/FCF (후행)", f"{last('pfcf'):.1f}배" if last("pfcf") else "—")
    k[2].metric("괴리", f"{last('gap'):+.1f}배" if last("gap") is not None else "—", help="P/FCF − P/E")
    k[3].metric("FCF 전환율", f"{last('conv') * 100:.0f}%" if last("conv") is not None else "—",
                help="FCF ÷ 순이익. 100% 아래로 떨어질수록 이익 대비 남는 현금이 적음")
    lines = valuation_reading(v.get("insight"))
    if lines:
        st.markdown("**지금 읽는 법**", help="계산된 수치를 정해진 문장 틀에 넣은 서술입니다(AI 미사용). 좋다·나쁘다 판정이나 투자 권유가 아닙니다.")
        st.markdown("\n".join(f"- {x}".replace("~", "\\~") for x in lines))  # '~' 두 개가 취소선이 되지 않게
    st.plotly_chart(valuation_chart(v), width="stretch", config={"displayModeBar": False})
    with st.expander("ⓘ 그래프 읽는 법"):
        st.markdown(VALUATION_GUIDE)
    st.caption("괴리 = P/FCF − P/E (0보다 위 = 이익보다 FCF가 적음). 마우스를 올리면 FCF 전환율도 보입니다.")
    st.plotly_chart(valuation_gap_chart(v), width="stretch", config={"displayModeBar": False})
    rows = [{
        "종목": r["ticker"],
        "P/E": "—" if r.get("missing") or r["pe"] is None else f"{r['pe']:.1f}",
        "P/FCF": "—" if r.get("missing") or r["pfcf"] is None else f"{r['pfcf']:.1f}",
        "FCF 전환율": "—" if r.get("missing") or r["conv"] is None else f"{r['conv'] * 100:.0f}%",
        "설비투자/영업현금": "—" if r.get("missing") or r["capex_share"] is None else f"{r['capex_share'] * 100:.0f}%",
        "최근 분기": "—" if r.get("missing") else (r.get("q_end") or "—"),
        "상태": status_text(r),
    } for r in v["latest"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"상태": st.column_config.TextColumn("상태", width="large",
                                help="데이터 상태와 계산상 주의점입니다(좋다·나쁘다 판정 아님). 최근 분기 = 지금 배수에 반영된 마지막 분기 말 — 분기 말 45일 뒤부터 반영")})
    miss = cv["missing"]
    st.caption(
        f":gray-background[참고용] 후행 12개월(TTM) 기준 — 분기 실적은 분기 말 {v['params']['report_lag_days']}일 뒤부터 반영. "
        f"그룹 배수 = Σ시가총액 ÷ Σ이익(또는 FCF), 반영 {len(cv['have'])}/{len(g.members)}종목"
        + (f" (수집 대기: {', '.join(miss)})" if miss else "")
        + ". 선행 P/E는 오늘부터 매일 누적(선행 P/FCF는 무료 데이터에 없음). "
        "재무: Alpha Vantage · 시세: Yahoo — 비공개 운영 단계 전용."
    )

if st.session_state.pop("_goto", None):
    st.switch_page("views/ticker.py")
