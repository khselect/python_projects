"""④ 종목 상세 — 다음 실적에 어떻게 반응할까 (F3~F7). 게시 JSON만 읽는다."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from charts import fan_chart, reaction_histogram
from common import coverage, tip
from pf.publish.ticker import load_published
from pf.sim.mixture import Mixture
from pf.sim.reaction_mc import draw_reaction, summarize


def pct(v, signed: bool = True) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"


def prob(v) -> str:
    return f"{v * 100:.0f}%"


@st.cache_data(ttl=300)
def published(ticker: str):
    return load_published(ticker)


cov = coverage()
st.title("④ 종목 상세")
st.caption("다음 실적에 어떻게 반응할까 — 과거 실적 반응으로 만든 확률 분포")

# 오른쪽 열은 ⑤ 종합 패널이 차지 (v0.16) — 비교 조회는 탭으로 이동
tickers = cov.tickers
if st.session_state.get("ticker") not in tickers:
    st.session_state["ticker"] = "AVGO"
ticker = st.selectbox("종목", tickers, key="ticker")
d = published(ticker)
if d is None:
    g = next(g for g in cov.industry if ticker in g.members)
    st.warning(f"{ticker} 계산 결과가 아직 없습니다.")
    st.code(f"docker compose exec market-app python -m pf.jobs.run publish --group {g.id}", language="bash")
    st.stop()

# ── 머리: 다음 실적일, 근거 배지 ─────────────────────────
ev = d["next_event"]
if ev:
    dday = (date.fromisoformat(ev["date"]) - date.fromisoformat(d["asof"])).days
    timing = {"AMC": "장 마감 후", "BMO": "장 시작 전"}.get(ev["timing"], "시각 미상")
    st.markdown(f"**다음 실적** {ev['date']} ({timing}) · **D-{dday}** · {d['group']['name']} 그룹, 벤치마크 {d['group']['benchmark']}")
s = d["sample"]
src = "합성 데이터(오프라인)" if d["source"] == "synthetic" else d["source"]
st.caption(
    f":gray-background[{d['gate']['status']}] 표본 {s['n_events']}건 ({s['first']} ~ {s['last']}) · "
    f"그룹 표본 {s['group_events']}건 · 기준일 {d['asof']} · 출처 {src} · "
    f"모델 자동 추정(태그 없음) · 시뮬레이션 {d['sim']['n_iter']:,}회"
)

# ── 확률 카드: 손실 쪽 숫자도 같은 크기 (§12.2 규칙 9) ────────
h1 = d["sim"]["horizons"]["1"]
st.markdown("**다음 날 초과수익률** (반응일, 벤치마크 대비)")
c = st.columns(3)
c[0].metric("P(상승)", prob(h1["p_up"]))
c[1].metric("P(하락)", prob(h1["p_down"]), help=tip("p_down"))
c[2].metric("기대값", pct(h1["mean"]))
c = st.columns(3)
c[0].metric("90% 구간 하단", pct(h1["pcts"]["5"]), help=tip("interval90"))
c[1].metric("90% 구간 상단", pct(h1["pcts"]["95"]), help=tip("interval90"))
c[2].metric("CVaR 5%", pct(h1["cvar5"]), help="가장 나쁜 5% 경우의 평균 초과수익률")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["다음 날 분포", "5·21·63일 누적", "시나리오 편집", "과거 반응", "비교 조회"])

with tab1:
    st.plotly_chart(
        reaction_histogram(h1["hist"], h1["pcts"]["5"], h1["pcts"]["95"]),
        width="stretch", config={"displayModeBar": False},
    )
    m = d["model"]["ticker"]
    st.dataframe(
        pd.DataFrame({
            "시나리오": m["labels"],
            "확률": [prob(w) for w in m["weights"]],
            "평균": [pct(v) for v in m["means"]],
            "척도": [pct(v, False) for v in m["scales"]],
        }),
        hide_index=True, width="stretch",
    )
    st.caption(
        f"반응일 초과수익률 = 종목 수익률 − β × {d['group']['benchmark']} 수익률. "
        f"3성분 t 혼합분포(자유도 {m['nu']:.0f})를 그룹 {d['group']['name']} 사전분포(가상 표본 κ={d['model']['kappa']})로 축소 추정."
    )

with tab2:
    st.plotly_chart(fan_chart(d["sim"]["fan"]), width="stretch", config={"displayModeBar": False})
    rows = []
    for h in ("1", "5", "21", "63"):
        x = d["sim"]["horizons"][h]
        rows.append({
            "기간": f"{h}거래일", "P(상승)": prob(x["p_up"]), "중앙값": pct(x["pcts"]["50"]),
            "90% 구간 하단": pct(x["pcts"]["5"]), "90% 구간 상단": pct(x["pcts"]["95"]), "CVaR 5%": pct(x["cvar5"]),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    a = d["sim"]["assumptions"]
    st.caption(
        f"2일차부터는 실적일을 뺀 최근 1년 일별 초과수익 변동성({a['sigma_daily'] * 100:.2f}%/일, t 분포)으로 누적. "
        "실적 후 추세는 0으로 가정합니다."
    )

with tab3:
    @st.fragment
    def scenario_editor(model: dict, base: dict, seed: int):
        st.caption("시나리오 확률·평균·표준편차를 바꾸면 50,000회로 다시 계산합니다 (원래 결과와 비교).")
        cols = st.columns(3)
        w, mu, sd = [], [], []
        for i, col in enumerate(cols):
            with col:
                st.markdown(f"**{model['labels'][i]}**")
                w.append(st.slider("확률(%)", 0, 100, int(round(model["weights"][i] * 100)), key=f"w{i}"))
                mu.append(st.slider("평균(%)", -30.0, 30.0, round(model["means"][i] * 100, 1), 0.5, key=f"m{i}"))
                sd.append(st.slider("표준편차(%)", 0.5, 20.0, max(0.5, round(model["scales"][i] * 100, 1)), 0.5, key=f"s{i}"))
        total = sum(w)
        if total == 0:
            st.warning("확률 합이 0입니다.")
            return
        mix = Mixture(tuple(x / total for x in w), tuple(x / 100 for x in mu), tuple(x / 100 for x in sd), model["nu"])
        r = summarize(draw_reaction(mix, 50_000, np.random.default_rng(seed)))
        st.caption(f"확률 합계 {total}% → 100%로 맞춰 계산")
        k = st.columns(3)
        k[0].metric("P(상승)", prob(r["p_up"]), f"{(r['p_up'] - base['p_up']) * 100:+.0f}%p")
        k[1].metric("P(하락)", prob(r["p_down"]), f"{(r['p_down'] - base['p_down']) * 100:+.0f}%p", delta_color="inverse")
        k[2].metric("기대값", pct(r["mean"]), f"{(r['mean'] - base['mean']) * 100:+.1f}%p")
        k = st.columns(3)
        k[0].metric("90% 구간 하단", pct(r["pcts"]["5"]), f"{(r['pcts']['5'] - base['pcts']['5']) * 100:+.1f}%p")
        k[1].metric("90% 구간 상단", pct(r["pcts"]["95"]), f"{(r['pcts']['95'] - base['pcts']['95']) * 100:+.1f}%p")
        k[2].metric("CVaR 5%", pct(r["cvar5"]), f"{(r['cvar5'] - base['cvar5']) * 100:+.1f}%p")

    scenario_editor(d["model"]["ticker"], h1, d["repro"]["seed"])

with tab4:
    hist = pd.DataFrame(d["history"])
    if hist.empty:
        st.info("과거 반응 기록이 없습니다.")
    else:
        view = pd.DataFrame({
            "발표일": hist["event_date"],
            "시점": hist["timing"].map({"AMC": "장후", "BMO": "장전"}).fillna("미상"),
            "반응일": hist["reaction_date"],
            "다음 날 수익률": hist["ret1"].map(pct),
            "다음 날 초과": hist["car1"].map(pct),
            "5일 누적": hist["car5"].map(pct),
            "21일 누적": hist["car21"].map(pct),
            "EPS 서프라이즈": hist["surprise_pct"].map(lambda v: "—" if v is None or pd.isna(v) else f"{v:+.1f}%"),
        })
        st.dataframe(view, hide_index=True, width="stretch")
        st.caption(f"최근 {len(view)}건 (전체 {s['n_events']}건). 누적은 벤치마크 대비 초과수익률.")

with tab5:
    others = [t for t in tickers if t != ticker]
    cmp_t = st.selectbox("비교할 종목", others, index=0, key="cmp_ticker")
    o = published(cmp_t)
    if o is None:
        st.caption("계산 결과 없음")
    else:
        rows = []
        for name, dd in ((ticker, d), (cmp_t, o)):
            x = dd["sim"]["horizons"]["1"]
            rows.append({
                "종목": name, "다음 실적": dd["next_event"]["date"] if dd["next_event"] else "—",
                "P(상승)": prob(x["p_up"]), "P(하락)": prob(x["p_down"]), "기대값": pct(x["mean"]),
                "90% 하단": pct(x["pcts"]["5"]), "90% 상단": pct(x["pcts"]["95"]),
                "CVaR 5%": pct(x["cvar5"]), "표본": dd["sample"]["n_events"],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
