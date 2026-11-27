"""⓪ 시장 개요 — 오늘 무엇이 움직였나. data/publish/overview.json만 읽는다.

market_monitor의 화면 패널 4개(주요 지수·원자재·미 국채·섹터)를 옮긴 것. 수치만 보여주고 판정은 ① 국면 점수가 한다.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from charts import sector_heatmap, yield_curve
from common import tip
from pf.macro.publish import MACRO_PATH
from pf.publish.overview import OVERVIEW_PATH
from pf.synth.rules import fmt_score

VIX_COLOR = {"안정": "blue", "보통": "gray", "위기": "red"}


@st.cache_data(ttl=300)
def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pct(v, nd=1):
    return "—" if v is None else f"{v * 100:+.{nd}f}%"


def num(v):
    if v is None:
        return "—"
    return f"{v:,.0f}" if abs(v) >= 1000 else (f"{v:,.2f}" if abs(v) >= 10 else f"{v:,.3f}")


st.title("⓪ 시장 개요")
st.caption("오늘 무엇이 움직였나 — 주요 지수·원자재·미 국채·섹터. 판정은 ① 매크로 국면에서 합니다")

d = _load(OVERVIEW_PATH)
if d is None:
    st.warning("시장 개요 계산 결과가 아직 없습니다.")
    st.code("docker compose exec market-jobs python -m pf.jobs.run overview", language="bash")
    st.stop()

# ── 상단 배지: VIX 국면 · 국면 점수 ───────────────────────
m = _load(MACRO_PATH)
b1, b2, b3 = st.columns([1, 1, 2])
vr = d.get("vix_regime")
if vr:
    b1.markdown(f"**VIX 국면** :{VIX_COLOR[vr['label']]}-background[{vr['label']}]",
                help=f"VIX {vr['window']}거래일 평균 {vr['avg']:.1f} · 안정 < {vr['thresholds'][0]} ≤ 보통 < "
                     f"{vr['thresholds'][1]} ≤ 위기 · 최근 1개월 최고 {vr['max_1m']:.1f}")
    b1.caption(f"5일 평균 {vr['avg']:.1f} · 1개월 최고 {vr['max_1m']:.1f}")
if m:
    color = "red" if m["regime"].startswith("위험회피") else ("blue" if m["regime"] == "확장" else "gray")
    b2.markdown(f"**국면** :{color}-background[{m['regime']}]", help=tip("regime_score"))
    b2.caption(f"국면 점수 {fmt_score(m['score'])}/{m.get('score_range', 6)}")
    if b3.button("① 국면 근거 보기 →", key="goto_macro"):
        st.switch_page("views/macro.py")
st.caption(f"기준일 {d['asof']} (종목마다 마지막 거래일이 다를 수 있음 · 한국·미국 휴장일)")

panels = d["panels"]


def price_table(items: list[dict], periods=("1D", "1M", "YTD")) -> pd.DataFrame:
    rows = []
    for i in items:
        if i.get("missing"):
            rows.append({"항목": i["name"], "가격": "—"})
            continue
        rows.append({"항목": i["name"], "가격": num(i["last"]), **{p: pct(i.get(p)) for p in periods},
                     "52주 위치": i.get("pos52"), "60일": i.get("spark") or []})
    return pd.DataFrame(rows)


def _styled(df: pd.DataFrame, cols):
    def color(v):
        if not isinstance(v, str) or v in ("—", ""):
            return ""
        return "color: #257de0" if v.startswith("+") else ("color: #ec4647" if v.startswith("-") else "")
    return df.style.map(color, subset=list(cols))


COLS = {
    "52주 위치": st.column_config.ProgressColumn("52주 위치", help="52주 최저(0) ~ 최고(100%) 사이 현재 위치",
                                              min_value=0, max_value=1, format="percent"),
    "60일": st.column_config.LineChartColumn("60일", width="small"),
}

# ── 주요 지수 ────────────────────────────────────────────
st.subheader(panels["indices"]["title"])
idx = panels["indices"]["items"]
for row in (idx[:4], idx[4:]):
    cols = st.columns(4)
    for c, i in zip(cols, row):
        if i.get("missing"):
            c.metric(i["name"], "—")
            continue
        c.metric(i["name"], num(i["last"]), pct(i.get("1D"), 2), chart_data=i.get("spark"), chart_type="line",
                 delta_color="inverse" if i["id"] == "VIX" else "normal", border=True,
                 help=f"1개월 {pct(i.get('1M'))} · YTD {pct(i.get('YTD'))} · 52주 고점 대비 {pct(i.get('from_hi'))}"
                      + (" · VIX는 오르면 불안이 커진다는 뜻이라 색을 반대로 표시" if i["id"] == "VIX" else ""))

# ── 원자재 · 미 국채 ─────────────────────────────────────
left, right = st.columns(2, gap="large")
with left:
    st.subheader(panels["commodities"]["title"])
    t = price_table(panels["commodities"]["items"])
    st.dataframe(_styled(t, ["1D", "1M", "YTD"]), hide_index=True, width="stretch", column_config=COLS)
with right:
    tr = panels["treasuries"]
    st.subheader(tr["title"])
    sp = tr.get("spread")
    if sp:
        st.caption(f"{sp['label']} {sp['bp']:+.0f}bp (1개월 {sp['bp_1m']:+.0f}bp)" + (" · ⚠️ 역전" if sp["inverted"] else ""),
                   help=tip("curve"))
    st.plotly_chart(yield_curve(tr["curve"]), width="stretch", config={"displayModeBar": False})
    rows = [{"만기": i["name"], "금리": "—" if i.get("missing") else f"{i['last']:.2f}%",
             **{f"{k} bp": ("—" if i.get("missing") or i["bp"][k] is None else f"{i['bp'][k]:+.0f}") for k in ("1D", "1W", "1M", "YTD")}}
            for i in tr["items"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ── 섹터 ─────────────────────────────────────────────────
st.subheader(panels["sectors"]["title"])
sec = [i for i in panels["sectors"]["items"] if not i.get("missing")]
above = sum(1 for i in sec if (i.get("vs_ma200") or 0) > 0)
st.caption(f"기간별 수익률(%) · ▲ 200일선 위 / ▽ 아래 — {above}/{len(sec)}개 위, 이 비율이 ① 시장 층의 '섹터 폭' 지표입니다 · "
           "색은 기간(열)마다 따로 비교 · 1개월 수익률 순",
           help=tip("sectors"))
st.plotly_chart(sector_heatmap(sec), width="stretch", config={"displayModeBar": False})

src = "합성 데이터(오프라인)" if d["source"].startswith("synthetic") else "Yahoo(개인 분석용) · FRED"
st.caption(f"출처: {src}. 지수·선물 시세는 비공개 운영 단계 전용입니다. {d['notice']['fred']} "
           f"[FRED API 약관]({d['notice']['terms_url']})")
