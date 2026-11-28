"""II. 매크로 국면 — 큰 자금은 어디로 움직이나 (F16). data/publish/macro.json만 읽는다."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from charts import market_compare, ratio_chart, regime_history, score_breakdown
from common import tip
from pf.macro.evaluate import load_eval
from pf.macro.publish import MACRO_PATH
from pf.synth.rules import fmt_score

SIG = {1.0: "▲ 우호", 0.0: "● 중립", -1.0: "▼ 비우호", None: "— 신호 없음"}
SIG_COLOR = {"▲ 우호": "#1757ac", "● 중립": "#666666", "▼ 비우호": "#c22b2c", "— 신호 없음": "#999999"}


@st.cache_data(ttl=300)
def macro():
    return json.loads(MACRO_PATH.read_text(encoding="utf-8")) if MACRO_PATH.exists() else None


def pct(v, signed=True):
    return "—" if v is None else (f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%")


def basis(ind: dict) -> str:
    v = ind["values"]
    k = ind["key"]
    if k == "liquidity":
        return (f"GDP 전년비 {v['gdp']:.1f}% − 기준금리 {v['rate']:.2f}% = {v['gap']:+.1f}%p · "
                f"6개월 금리 {v['drate6m']:+.2f}%p") if v.get("gap") is not None else "데이터 부족"
    if k == "commodity":
        return f"DBC 200일선 대비 {pct(v['vs_ma'])} · 52주 고점 대비 {pct(v['vs_high'])}"
    if k == "breadth":
        s = f"RSP/SPY 200일선 대비 {pct(v['vs_ma'])} · 52주 고점 대비 {pct(v['vs_high'])}"
        return s + (" · ⚠️ 지수 고점 근처인데 폭 약화(괴리)" if v.get("divergence") else "")
    if k == "credit":
        return f"하이일드 스프레드 3개월 {v['direction']} (값은 데이터 라이선스상 비공개)" if v.get("direction") else "최근 3년 데이터만 제공"
    if k == "curve":
        d = v.get("days_since_inv")
        since = "역전 이력 없음" if d is None or d >= 10_000 else ("현재 역전" if d == 0 else f"역전 해소 후 {int(d)}일")
        return f"10Y−2Y {v['level']:+.2f}%p · {since}"
    if k == "dollar":
        return f"광의 달러지수 200일선 대비 {pct(v['vs_ma'])} · 6개월 {pct(v['6m'])}"
    if k == "vix":
        return f"VIX {v['level']:.1f} · 최근 1개월 최고 {v['max_1m']:.1f}" if v.get("level") is not None else "데이터 없음"
    if k == "trend":
        if v.get("spx_vs_ma") is None:
            return "데이터 부족"
        return (f"S&P500 200일선 대비 {pct(v['spx_vs_ma'])}·고점 대비 {pct(v['spx_dd'])} · "
                f"나스닥100 200일선 대비 {pct(v['ndx_vs_ma'])}·고점 대비 {pct(v['ndx_dd'])}")
    if k == "sectors":
        return (f"200일선 위 섹터 {v['share'] * 100:.0f}% ({round(v['share'] * v['n'])}/{int(v['n'])}개)"
                if v.get("share") is not None else "데이터 부족")
    if k == "rates":
        return (f"2년물 {v['y2']:.2f}% · 1개월 {v['d1m']:+.2f}%p" if v.get("d1m") is not None else "데이터 부족")
    return ""


st.title("II. 매크로 국면")
st.caption("큰 자금은 어디로 움직이나 — 느린 매크로 층 6개 + 빠른 시장 층 4개, 10개 지표의 방향으로 국면을 판정합니다")

d = macro()
if d is None:
    st.warning("매크로 계산 결과가 아직 없습니다.")
    st.code("docker compose exec market-jobs python -m pf.jobs.run macro", language="bash")
    st.stop()

rng = d.get("score_range", 6)
th = d["thresholds"]
layers = d.get("layers") or {}

# ── 국면 배너 ────────────────────────────────────────────
c1, c2, c3 = st.columns([1, 1.5, 2])
c1.metric("국면 점수", f"{fmt_score(d['score'])} / {rng}", help=tip("regime_score"))
c2.metric("국면", d["regime"], help=f"+{th['expansion']} 이상 확장 · {th['riskoff']} 이하 위험회피 · 그 사이 중립·전환 · 급변 규칙 우선")
lay = " · ".join(f"{v['name']} {fmt_score(v['score'])}/{v['n']} ({v['confirm_days']}일 확정)" for v in layers.values())
c3.markdown(
    f"**{d['regime_since']}**부터 이 국면  \n"
    f"기준일 {d['asof']} · 신호 {d['n_signals']}/{rng}개  \n{lay}"
)
stress = d.get("stress") or {}
if stress.get("on"):
    since = f" ({stress['since']}부터)" if stress.get("since") else ""
    if stress.get("entry_today", True):
        why = " · ".join(w for w, on in (("VIX 30 이상", stress.get("vix")), ("나스닥100 고점 대비 −20% 이하", stress.get("ndx_dd"))) if on)
        st.error(f"**급변 규칙 발동{since}** — {why}. 점수와 관계없이 위험회피(급변)로 표시합니다.", icon="⚠️")
    else:
        st.error(f"**급변 규칙 유지{since}** — 진입 조건은 풀렸지만 해제 조건을 기다리는 중입니다 "
                 f"(진정 {stress.get('calm_run', 0)}/{stress.get('exit_days', 5)}거래일). {stress.get('exit_rule', '')}.",
                 icon="⚠️")

# ── 점수 분해 ────────────────────────────────────────────
st.markdown(f"**왜 {fmt_score(d['score'])}점인가 — 지표별 기여**", help="막대 하나가 지표 하나의 확정 신호(+1·0·−1)입니다. 마우스를 올리면 지금 값을 보여줍니다.")
for ind in d["indicators"]:
    ind["basis"] = basis(ind)
labels = {k: v["name"] for k, v in layers.items()} or {"macro": "매크로 층"}
for ind in d["indicators"]:
    ind.setdefault("layer", "macro")
st.plotly_chart(score_breakdown(d["indicators"], labels), width="stretch", config={"displayModeBar": False})

# ── 비교 기준 (상대 기준) ─────────────────────────────────
if "compare_base" not in st.session_state:
    st.session_state["compare_base"] = "6개월 전"
base_label = st.segmented_control("비교 기준", ["3개월 전", "6개월 전", "1년 전"], key="compare_base")
months = {"3개월 전": "3", "6개월 전": "6", "1년 전": "12"}[base_label or "6개월 전"]
cmp = d["compare"][months]
st.caption(f"{base_label} ({cmp['date']}): 국면 점수 {fmt_score(cmp['score'])} · {cmp['regime']}  →  현재 {fmt_score(d['score'])} · {d['regime']}")

# ── 지표 체크리스트 ───────────────────────────────────────
rows = []
for ind in d["indicators"]:
    before = SIG.get(cmp["signals"][ind["key"]], SIG[None])
    now = SIG.get(ind["signal"], SIG[None])
    rows.append({
        "지표": ind["name"],
        "층": labels.get(ind["layer"], ""),
        base_label: before,
        "현재": now,
        "변화": "전환" if before != now else "",
        "마지막 전환": ind["last_switch"] or "—",
        "근거": basis(ind),
    })
table = pd.DataFrame(rows)
styled = table.style.map(lambda v: f"color: {SIG_COLOR[v]}; font-weight: 600" if v in SIG_COLOR else "",
                         subset=[base_label, "현재"])
st.dataframe(styled, hide_index=True, width="stretch")
with st.expander("ⓘ 지표별 판정 기준"):
    for ind in d["indicators"]:
        st.markdown(f"**{ind['name']}** — {tip(ind['key'])}")

# ── 2년 추이 ─────────────────────────────────────────────
st.markdown("**국면 점수 2년 추이** (주간 · 막대 = 층별 점수, 선 = 합계, 진한 빨강 배경 = 급변 규칙 발동 주)")
h = d["history"]
st.plotly_chart(
    regime_history(h["dates"], h["score"], th["expansion"], th["riskoff"], macro=h.get("macro"), market=h.get("market"),
                   stress=h.get("stress"), rng=rng),
    width="stretch", config={"displayModeBar": False},
)
# 지수 비교 배경용: 급변 주는 위험회피로
eff = [th["riskoff"] if st_ else sc for sc, st_ in zip(h["score"], h.get("stress") or [False] * len(h["score"]))]

# ── 검증: 과거 스트레스 구간을 얼마나 빨리 잡았나 ───────────
ev = load_eval()
if ev:
    vs = ev["variants"]
    v6, v10 = vs["v6"], vs["v10"]
    vi = vs.get("v10i")
    with st.expander(f"검증 — 과거 하락 구간 탐지 ({ev['period'][0][:4]}~{ev['period'][1][:4]}, 설계안 {len(vs)}개 비교)"):
        def cmp(key, fmt):
            parts = [f"v0.21 {fmt(vi[key])}"] if vi else []
            return " · ".join(parts + [f"기존안 {fmt(v6[key])}"])

        k = st.columns(4)
        k[0].metric("탐지 (현재안)", f"{v10['detected']}/{v10['detected'] + v10['missed']}",
                    cmp("detected", lambda x: str(x)), delta_color="off", delta_arrow="off")
        md = lambda x: "—" if x is None else f"{x:+.0f}일"  # noqa: E731
        k[1].metric("−10% 도달일 대비 (중앙)", md(v10["median_vs_confirm10"]), cmp("median_vs_confirm10", md),
                    delta_color="off", delta_arrow="off",
                    help="음수면 S&P 500이 52주 고점 대비 −10%에 닿기 전에 위험회피로 바뀌었다는 뜻 (거래일)")
        k[2].metric("오경보 (연)", f"{v10['false_alarms_per_year']:.2f}", cmp("false_alarms_per_year", lambda x: f"{x:.2f}"),
                    delta_color="off", delta_arrow="off",
                    help="위험회피로 들어갔는데 이후 63거래일 최대 낙폭이 −7%보다 얕았던 횟수")
        k[3].metric("위험회피 비중", f"{v10['riskoff_share']:.0%}", cmp("riskoff_share", lambda x: f"{x:.0%}"),
                    delta_color="off", delta_arrow="off", help="전체 기간 중 위험회피(점수 ≤ 하단 또는 급변)였던 날의 비율")
        if "false_riskoff_share" in v10:
            k2 = st.columns(4)
            k2[0].metric("헛 위험회피 일수", f"{v10['false_riskoff_share']:.0%}", cmp("false_riskoff_share", lambda x: f"{x:.0%}"),
                         delta_color="off", delta_arrow="off",
                         help="하락 구간(고점 30일 전 ~ 저점) 밖에서 위험회피였던 날의 비율. 오경보 횟수는 진입만 세므로, "
                              "오래 머무는 설계의 비용은 이 값으로 봅니다")
            k2[1].metric("하락 구간 중 위험회피", f"{v10['riskoff_in_episodes']:.0%}", cmp("riskoff_in_episodes", lambda x: f"{x:.0%}"),
                         delta_color="off", delta_arrow="off", help="하락 구간(고점 30일 전 ~ 저점) 날 중 위험회피였던 비율 — 높을수록 하락을 오래 잡고 있음")

        def cell(r):
            if r["detected"] is None:
                return "놓침"
            if r["already_on"]:
                return "고점 전부터 위험회피"
            return f"{r['detected']} (고점 후 {r['lag_from_peak']}일 · −10% 대비 {r['vs_confirm10']:+d}일)"

        rows = []
        for i, e in enumerate(ev["episodes"]):
            row = {"고점": e["peak"], "저점": e["trough"], "낙폭": f"{e['depth'] * 100:.1f}%", "기존안(6개)": cell(v6["per_episode"][i])}
            if vi:
                row["v0.21(즉시 해제)"] = cell(vi["per_episode"][i])
            row["현재안(히스테리시스)"] = cell(v10["per_episode"][i])
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(f"하락 구간 = S&P 500이 52주 고점 대비 {ev['rules']['episode_dd'] * 100:.0f}% 이상 빠진 구간. "
                   "기존안은 매크로 6개·경계 ±3, v0.21은 10개·경계 ±4 + 급변 규칙(조건이 풀린 날 바로 해제), "
                   "현재안은 급변 해제에 히스테리시스(VIX 25 미만·나스닥100 −15%보다 회복이 5거래일 연속). "
                   f"{ev.get('note', '')}. 과거 구간에 맞춰 경계를 고르면 과적합이 될 수 있어, 경계를 바꿀 때는 근거를 PLAN에 기록합니다.")

# ── 지수 비교 (Nasdaq-100 · S&P 100) ─────────────────────
mk = d.get("markets")
if mk:
    st.markdown("**지수 비교 — Nasdaq-100 · S&P 100** (같은 2년, 시작 주 = 100)")
    k = st.columns(len(mk["series"]) + 1)
    for i, t in enumerate(mk["series"]):
        k[i].metric(mk["names"][t], f"{mk['change'][t] * 100:+.1f}%", help="2년 전 같은 주 대비 (주간 종가 기준)")
    k[-1].metric("QQQ/OEF 비율", f"{mk['ratio'][-1] - 100:+.1f}%", help="+면 기술주 중심(Nasdaq-100)이 대형주 전체(S&P 100)보다 강했다는 뜻")
    st.plotly_chart(market_compare(mk, h["dates"], eff, th["expansion"], th["riskoff"]),
                    width="stretch", config={"displayModeBar": False})
    st.caption("QQQ/OEF 비율 (시작 = 100) — 오르면 기술주 쪽이 더 강함")
    st.plotly_chart(ratio_chart(mk), width="stretch", config={"displayModeBar": False})
    st.caption("배경 = 국면 점수 추이의 확장(파랑)·위험회피(빨강) 주. 국면 점수에는 쓰지 않는 참고 비교이며, "
               "QQQ/OEF 비율은 시장 폭(RSP/SPY)처럼 상승이 기술주에 쏠렸는지 보는 보조선입니다. "
               "ETF 시세(Yahoo) 기반 — 비공개 운영 단계 전용.")
else:
    st.caption("지수 비교(Nasdaq-100·S&P 100)는 다음 매일 배치 뒤 표시됩니다.")

st.info("자산군 가이드(같은 국면이었던 과거의 주식·채권·원자재·달러 성과)는 v1에서 추가됩니다.", icon="🛠️")
src = "합성 데이터(오프라인)" if d["source"].startswith("synthetic") else "FRED · Yahoo(개인 분석용)"
st.caption(f"출처: {src}. {d['notice']['fred']} [FRED API 약관]({d['notice']['terms_url']})")
