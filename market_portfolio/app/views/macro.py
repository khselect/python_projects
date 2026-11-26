"""① 매크로 국면 — 큰 자금은 어디로 움직이나 (F16). data/publish/macro.json만 읽는다."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from charts import market_compare, ratio_chart, regime_history
from common import tip
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
    return ""


st.title("① 매크로 국면")
st.caption("큰 자금은 어디로 움직이나 — 6개 지표의 방향 전환으로 국면을 판정합니다")

d = macro()
if d is None:
    st.warning("매크로 계산 결과가 아직 없습니다.")
    st.code("docker compose exec market-jobs python -m pf.jobs.run macro", language="bash")
    st.stop()

# ── 국면 배너 ────────────────────────────────────────────
c1, c2, c3 = st.columns([1, 1, 2])
c1.metric("국면 점수", fmt_score(d['score']), help=tip("regime_score"))
c2.metric("국면", d["regime"], help="+3 이상 확장 · −3 이하 위험회피 · 그 사이 중립·전환")
c3.markdown(
    f"**{d['regime_since']}**부터 이 국면  \n"
    f"기준일 {d['asof']} · 신호 {d['n_signals']}/6개 · 각 신호는 5거래일 연속 유지돼야 전환으로 인정 · 지표마다 우호(+1)·중립(0)·비우호(−1)"
)

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
st.markdown("**국면 점수 2년 추이** (주간)")
h = d["history"]
st.plotly_chart(
    regime_history(h["dates"], h["score"], d["thresholds"]["expansion"], d["thresholds"]["riskoff"]),
    width="stretch", config={"displayModeBar": False},
)

# ── 지수 비교 (Nasdaq-100 · S&P 100) ─────────────────────
mk = d.get("markets")
if mk:
    st.markdown("**지수 비교 — Nasdaq-100 · S&P 100** (같은 2년, 시작 주 = 100)")
    k = st.columns(len(mk["series"]) + 1)
    for i, t in enumerate(mk["series"]):
        k[i].metric(mk["names"][t], f"{mk['change'][t] * 100:+.1f}%", help="2년 전 같은 주 대비 (주간 종가 기준)")
    k[-1].metric("QQQ/OEF 비율", f"{mk['ratio'][-1] - 100:+.1f}%", help="+면 기술주 중심(Nasdaq-100)이 대형주 전체(S&P 100)보다 강했다는 뜻")
    st.plotly_chart(market_compare(mk, h["dates"], h["score"], d["thresholds"]["expansion"], d["thresholds"]["riskoff"]),
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
