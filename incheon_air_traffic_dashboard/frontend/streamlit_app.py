"""인천 1호선 초미세먼지 · 통행량 통합 분석 대시보드 (Streamlit 프론트엔드)

백엔드(FastAPI + PostgreSQL)에서 데이터를 받아
1. 데이터 업로드·관리 / 2. 추세·기간예측 / 3. 교차분석 / 4. 지도 / 5. 종합 리포트
5개 탭으로 구성한다. 원본 엑셀(통행량·초미세먼지)은 탭1에서 업로드하면
월 단위로 DB에 누적 적재되고, 누적분은 예측·분석·리포트에 그대로 활용된다.
"""
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_common import get_stations, pm25_stations, api_get, api_post_file

st.set_page_config(page_title="인천 1호선 초미세먼지·통행량 대시보드", layout="wide")

# 한 화면(스크롤 최소화) 레이아웃: 기본 여백·타이포를 전체적으로 압축
st.markdown("""
<style>
  /* 고정 상단 헤더 바를 숨김 — 숨기지 않으면 줄여둔 상단 여백에서 제목이 바 밑에 깔려 잘려 보임 */
  header[data-testid="stHeader"] { display: none; }
  .block-container { padding-top: 1.1rem; padding-bottom: 0.6rem; }
  h1 { font-size: 1.3rem !important; margin-bottom: 0 !important; line-height: 1.5 !important; padding-top: 0 !important; }
  h3 { font-size: 1.02rem !important; margin: 0 0 .2rem 0 !important; }
  p, li, .stMarkdown { font-size: 0.86rem; }
  [data-testid="stCaptionContainer"] { font-size: 0.74rem; }
  [data-testid="stMetricValue"] { font-size: 1.25rem; }
  [data-testid="stMetricLabel"] { font-size: 0.74rem; }
  [data-testid="stAlert"] p { font-size: 0.8rem; }
  div[data-testid="stDataFrame"] { font-size: 0.8rem; }
  .stTabs [data-baseweb="tab"] p { font-size: 0.85rem; }
  hr { margin: .4rem 0; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 인천 1호선 초미세먼지 · 통행량 통합 분석 대시보드")
st.caption("초미세먼지(PM2.5) 시간대별 월보 · 역·시간대별 통행량 · 역사 위치 기반 통합 시각화")

try:
    stations = get_stations()
except Exception as e:
    st.error(f"백엔드 API({e.__class__.__name__})에 연결할 수 없습니다. backend 서비스가 기동 중인지 확인하세요.")
    st.stop()

pm_stations = pm25_stations(stations)
DEFAULT_STATION = "인천대입구"

# 적재된 데이터셋 현황 (통행량 기준월 / PM2.5 월 목록) — 업로드 시 자동 갱신
datasets = api_get("/api/datasets")
periods = [d["period"] for d in datasets["traffic"]]
pm_months = [d["month"] for d in datasets["pm25"]]

# 통행량은 항상 최신 기준월 사용 (탭2·탭3) — 사이드바 선택 UI는 화면 공간 문제로 제거
period = periods[-1] if periods else None
period_kr = period.replace("-", "년 ") + "월" if period else "-"
period_params = {"period": period} if period else {}

# 데이터 업로드·관리를 첫 탭으로 배치 (원본 적재가 모든 분석의 출발점)
tab4, tab1, tab2, tab3, tab5 = st.tabs([
    "1. 데이터 업로드 · 관리", "2. 추세 · 기간예측", "3. 미세먼지-통행량 교차분석",
    "4. 혼잡도-미세먼지 지도", "5. 종합 리포트",
])

# ============================================================
# 탭 1: 추세 · 기간예측
# ============================================================
with tab1:
    st.subheader("과제1. 역사별 시간대별 초미세먼지 추세 · 기간예측")
    c0, c1, c2, c3, c4, c5 = st.columns(6)
    pm_month_options = ["전체(누적)"] + pm_months
    pm_month_sel = c0.selectbox("PM2.5 기준월", pm_month_options, index=0,
                                 format_func=lambda m: m if m == "전체(누적)" else m.replace("-", "년 ") + "월",
                                 help="'전체(누적)'는 업로드된 모든 월의 데이터를 학습 구간으로 사용합니다.")
    station = c1.selectbox("측정소(역)", pm_stations,
                            index=pm_stations.index(DEFAULT_STATION) if DEFAULT_STATION in pm_stations else 0)
    start_day = c2.number_input("시작일(해당 월의 일)", min_value=1, max_value=31, value=1)
    end_day = c3.number_input("종료일(해당 월의 일)", min_value=1, max_value=31, value=31)
    model = c4.selectbox("예측 모델", ["seasonal", "linear"],
                          format_func=lambda v: "계절성 분해(요일×시간대 패턴)" if v == "seasonal" else "선형회귀 / 추세선")
    horizon = c5.selectbox("예측 기간", [3, 7, 14], index=1, format_func=lambda v: f"향후 {v}일")

    if start_day > end_day:
        st.warning("시작일은 종료일보다 작거나 같아야 합니다.")
    else:
        forecast_params = {
            "station": station, "start_day": start_day, "end_day": end_day,
            "model": model, "horizon_days": horizon,
        }
        if pm_month_sel != "전체(누적)":
            forecast_params["month"] = pm_month_sel
        data = api_get("/api/trend/forecast", forecast_params)
        st.info(data["note"])

        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("구간 평균(㎍/㎥)", f"{data['stat_avg']:.1f}")
        s2.metric("구간 최고", f"{data['stat_max']:.1f}")
        s3.metric("구간 최저", f"{data['stat_min']:.1f}")
        s4.metric("기준(35) 초과시간", f"{data['stat_over35_hours']}시간 ({data['stat_over35_ratio']:.1f}%)")
        s5.metric("예측기간 평균(㎍/㎥)", f"{data['stat_forecast_avg']:.1f}")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data["hist_labels"], y=data["hist_values"],
                                  mode="lines", name="실측 PM2.5", line=dict(color="#2563eb", width=1.6)))
        # 예측선이 실측 마지막 지점에서 이어지도록 시작점을 붙여준다
        fore_x = [data["hist_labels"][-1]] + data["forecast_labels"]
        fore_y = [data["hist_values"][-1]] + data["forecast_values"]
        fig.add_trace(go.Scatter(x=fore_x, y=fore_y, mode="lines",
                                  name=f"예측 PM2.5 ({'계절성분해' if model=='seasonal' else '선형회귀'})",
                                  line=dict(color="#f97316", width=2, dash="dash")))
        fig.add_hline(y=35, line_dash="dot", line_color="#dc2626", annotation_text="환경기준(35㎍/㎥, 나쁨)")
        fig.update_layout(height=330, xaxis_title="시간", yaxis_title="PM2.5 (㎍/㎥)",
                           legend=dict(orientation="h", y=1.08), margin=dict(t=30))
        fig.update_xaxes(tickmode="auto", nticks=14)
        st.plotly_chart(fig, use_container_width=True)

    st.caption(
        f"데이터: 초미세먼지 월보(1시간 평균) 누적 {len(pm_months)}개월({', '.join(pm_months) if pm_months else '-'}). "
        "예측은 과거 패턴 기반 통계적 추정이며, 누적 개월이 늘수록 요일×시간대 패턴 추정이 안정됩니다."
    )

# ============================================================
# 탭 2: 미세먼지-통행량 교차분석
# ============================================================
with tab2:
    st.subheader("과제2. 초미세먼지 × 역 통행량 교차분석")
    st.warning(
        f"⚠ 두 자료의 수집 시기가 다릅니다 — 초미세먼지: 2024년 10월(00시–24시 1시간 단위) / "
        f"통행량: {period_kr}(05시–24시 이후 20구간). 따라서 절대 시점 비교가 아닌 **하루 중 시간대별 평균 패턴** "
        f"간의 교차 비교이며, 초미세먼지의 0시대 데이터를 통행량의 '24시이후' 구간에 대응시켰습니다."
    )
    station2 = st.selectbox("역 선택(공통 28개 역)", pm_stations, key="station2",
                             index=pm_stations.index(DEFAULT_STATION) if DEFAULT_STATION in pm_stations else 0)

    cc1, cc2 = st.columns([1.3, 1])
    with cc1:
        cross = api_get(f"/api/cross/{station2}", period_params)
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=cross["hour_labels"], y=cross["traffic_total"],
                               name="통행량(승차+하차)", marker_color="rgba(37,99,235,.5)", yaxis="y"))
        fig2.add_trace(go.Scatter(x=cross["hour_labels"], y=cross["pm_aligned"], name="PM2.5 평균(㎍/㎥)",
                                   mode="lines+markers", line=dict(color="#f97316", width=2), yaxis="y2"))
        fig2.update_layout(
            height=310,
            yaxis=dict(title="통행량(명)"),
            yaxis2=dict(title="PM2.5(㎍/㎥)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1), margin=dict(t=30),
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.metric(f"{station2} 시간대 패턴 상관계수", f"{cross['correlation']*100:.1f}%")

    with cc2:
        scatter = api_get("/api/cross/", period_params)
        df = pd.DataFrame(scatter["points"])

        # 사분면 분할 기준: 공통 역 전체 평균 (수직선 = PM2.5 평균, 수평선 = 통행량 평균)
        x_th = df["avg_pm25"].mean()
        y_th = df["total_traffic"].mean()

        def _quadrant_group(r):
            if r["station"] == station2:
                return "선택역"
            if r["avg_pm25"] >= x_th and r["total_traffic"] >= y_th:
                return "우선관리"
            return "일반"

        df["grp"] = df.apply(_quadrant_group, axis=1)
        priority = df[(df["avg_pm25"] >= x_th) & (df["total_traffic"] >= y_th)] \
            .sort_values("total_traffic", ascending=False)

        st.markdown("**역별 사분면 우선순위 산점도 — PM2.5 × 월 통행량 (공통 역 전체)**")
        fig3 = go.Figure()
        # 우상단(고농도·고혼잡) 사분면 음영
        fig3.add_shape(type="rect", x0=x_th, y0=y_th,
                       x1=df["avg_pm25"].max() * 1.1, y1=df["total_traffic"].max() * 1.08,
                       fillcolor="rgba(220,38,38,.07)", line_width=0, layer="below")
        fig3.add_vline(x=x_th, line_dash="dot", line_color="#94a3b8", line_width=1)
        fig3.add_hline(y=y_th, line_dash="dot", line_color="#94a3b8", line_width=1)

        for grp, name, mcolor, msize, tcolor, tsize in [
            ("일반", "일반 역", "rgba(37,99,235,.55)", 8, "#94a3b8", 9),
            ("우선관리", "고혼잡·고농도(우선순위 사분면)", "#dc2626", 11, "#dc2626", 10),
            ("선택역", "선택역", "#0f172a", 13, "#0f172a", 10),
        ]:
            sub = df[df["grp"] == grp]
            fig3.add_trace(go.Scatter(
                x=sub["avg_pm25"], y=sub["total_traffic"],
                mode="markers+text", name=name, text=sub["station"],
                textposition="middle right", textfont=dict(size=tsize, color=tcolor),
                marker=dict(color=mcolor, size=msize),
                hovertemplate="%{text}<br>PM2.5 %{x:.1f}㎍/㎥<br>월 통행량 %{y:,}명<extra></extra>",
            ))
        fig3.update_layout(height=310, xaxis_title="PM2.5 월평균(㎍/㎥)", yaxis_title="월 통행량 합계(명)",
                            legend=dict(orientation="h", y=-0.28), margin=dict(t=10))
        st.plotly_chart(fig3, use_container_width=True)

        st.metric("공통 역 전체 기준 상관계수", f"{scatter['correlation']*100:.1f}%")
        if not priority.empty:
            st.markdown(
                "🔴 **주요 관리역** (PM2.5·통행량 모두 전체 평균 이상, 통행량순): "
                + ", ".join(priority["station"])
            )
        st.caption(
            f"사분면 기준선 = 공통 {len(df)}개 역 전체 평균 (PM2.5 {x_th:.1f}㎍/㎥ · 월 통행량 {y_th:,.0f}명). "
            "우상단 음영 구역이 고농도·고혼잡 동시 해당 역으로, 환기설비 점검·혼잡 분산의 우선 검토 대상입니다. "
            "상관계수는 선택 역과 무관한 전체 기준 상수입니다."
        )

# ============================================================
# 탭 3: 혼잡도-미세먼지 지도
# ============================================================
with tab3:
    st.subheader("과제3. 역사 위치 기반 혼잡도-미세먼지 상관관계 지도")
    st.info(
        f"위치 좌표: 인천교통공사 공식 역정보(도로명주소) 및 공개 지리정보 기반 근사좌표입니다. "
        f"원(마커) 크기 = 월 통행량(승차+하차 합, {period_kr}), 색상 = PM2.5 평균"
        f"({', '.join(pm_months) if pm_months else '-'} 누적 기준) "
        f"(회색 = 미세먼지 측정소 없음: 검단호수공원·신검단중앙·아라·계양·귤현)."
    )
    mapdata = api_get("/api/map", period_params)
    df_map = pd.DataFrame(mapdata["points"])

    m1, m2 = st.columns([1.4, 1])
    with m1:
        # folium(Leaflet)은 비활성 탭 안에서 0×0 크기로 초기화되어 지도가 표시되지 않는
        # 문제가 있어(streamlit-folium in st.tabs), 탭 가시성을 정상 처리하는 Plotly 지도로 렌더링.
        max_cong = df_map["congestion"].max() or 1

        def pm_color(v):
            if v is None or pd.isnull(v):
                return "#94a3b8"
            if v < 15: return "#22c55e"
            if v < 25: return "#84cc16"
            if v < 35: return "#eab308"
            if v < 50: return "#f97316"
            return "#dc2626"

        sizes = [10 + 30 * ((c or 0) / max_cong) ** 0.5 for c in df_map["congestion"]]
        colors = [pm_color(v) for v in df_map["avg_pm25"]]
        hovers = [
            f"<b>{r['station']}</b><br>"
            f"평균 PM2.5: {('%.1f㎍/㎥' % r['avg_pm25']) if pd.notnull(r['avg_pm25']) else '측정소 없음'}<br>"
            f"월 통행량(승하차 합): {int(r['congestion']):,}명"
            for _, r in df_map.iterrows()
        ]

        fig_map = go.Figure()
        # df_map은 /api/map 응답 순서(line_order)를 유지하므로 그대로 노선 폴리라인이 됨
        fig_map.add_trace(go.Scattermapbox(
            lat=df_map["lat"], lon=df_map["lon"], mode="lines",
            line=dict(width=3, color="#94a3b8"), hoverinfo="skip", name="1호선",
        ))
        fig_map.add_trace(go.Scattermapbox(
            lat=df_map["lat"], lon=df_map["lon"], mode="markers",
            marker=dict(size=sizes, color=colors, opacity=0.85),
            text=hovers, hoverinfo="text", name="역",
        ))
        fig_map.update_layout(
            mapbox=dict(style="open-street-map", center=dict(lat=37.48, lon=126.70), zoom=10.3),
            height=430, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
        )
        st.plotly_chart(fig_map, use_container_width=True)

    with m2:
        st.metric("통행량-PM2.5 상관계수(28개 역)", f"{mapdata['correlation']*100:.1f}%")
        st.markdown("🟢 15 미만 · 🟡 15–25 · 🟠 25–35 · 🔴 35–50 · 🟥 50 이상 (㎍/㎥)")

        # 상위 5개 역 두 목록을 좌우로 나란히 — 스크롤 없이 지도 높이 안에 수납
        def _mini_table(title, items, value_of):
            rows = "".join(
                f"<tr><td style='padding:1px 4px;white-space:nowrap'>{i+1}. {p['station']}</td>"
                f"<td style='padding:1px 4px;text-align:right;white-space:nowrap'>{value_of(p)}</td></tr>"
                for i, p in enumerate(items)
            )
            return (f"<div style='flex:1;min-width:0'><b style='font-size:12.5px'>{title}</b>"
                    f"<table style='width:100%;font-size:12px;line-height:1.5;border-collapse:collapse'>{rows}</table></div>")

        st.markdown(
            "<div style='display:flex;gap:14px;margin-top:6px'>"
            + _mini_table("통행량 상위 5개 역", mapdata["top_congestion"],
                          lambda p: f"월 {p['congestion']:,}명 · {p['avg_pm25']:.1f}㎍")
            + _mini_table("PM2.5 상위 5개 역", mapdata["top_pm25"],
                          lambda p: f"{p['avg_pm25']:.1f}㎍ · 월 {p['congestion']:,}명")
            + "</div>",
            unsafe_allow_html=True,
        )

# ============================================================
# 탭 4: 데이터 업로드 · 관리
# ============================================================
with tab4:
    st.subheader("데이터 업로드 · 적재 현황")
    st.info(
        "원본 엑셀을 업로드하면 월 단위로 DB에 **누적** 적재됩니다 — 같은 월을 다시 올리면 그 월만 교체되고 "
        "다른 월 데이터는 유지됩니다. 누적된 데이터는 예측 모델(탭1)·교차분석(탭2)·지도(탭3)·리포트(탭5)에 즉시 반영됩니다."
    )
    if "upload_msg" in st.session_state:
        st.success(st.session_state.pop("upload_msg"))

    up1, up2 = st.columns(2)
    with up1:
        st.markdown("**① 역·시간대별 통행량 업로드** — 시트 `1호선 `(역명/구분/시간대별 인원)")
        tfile = st.file_uploader("통행량 xlsx 선택", type=["xlsx"], key="up_traffic")
        default_period = ""
        if tfile is not None:
            m = re.search(r"(\d{4})\s*[.\-_년\s]\s*(\d{1,2})\s*월?", tfile.name)
            if m:
                default_period = f"{m.group(1)}-{int(m.group(2)):02d}"
        period_in = st.text_input("자료 기준월 (YYYY-MM)", value=default_period,
                                   placeholder="예: 2026-06", key="up_traffic_period",
                                   help="파일명에 '2026년 6월' 형태가 있으면 자동으로 채워집니다.")
        if st.button("통행량 적재", disabled=(tfile is None or not period_in), key="btn_traffic"):
            try:
                res = api_post_file("/api/upload/traffic", tfile.name, tfile.getvalue(),
                                     {"period": period_in})
                msg = f"{res['period']} 통행량 {res['records']:,}건 적재 완료 (역 {res['stations']}개)"
                if res.get("skipped_stations"):
                    msg += f" · 미등록 역 제외: {', '.join(res['skipped_stations'])}"
                st.session_state["upload_msg"] = msg
                st.rerun()
            except RuntimeError as e:
                st.error(f"적재 실패: {e}")

    with up2:
        st.markdown("**② 초미세먼지 월보 업로드** — 시트 `공단양식`(역명/측정시간/측정값)")
        pfile = st.file_uploader("초미세먼지 xlsx 선택", type=["xlsx"], key="up_pm25")
        st.caption("기준월은 파일 안의 측정시간(YYYYMMDDHH)에서 자동 인식됩니다.")
        if st.button("초미세먼지 적재", disabled=(pfile is None), key="btn_pm25"):
            try:
                res = api_post_file("/api/upload/pm25", pfile.name, pfile.getvalue())
                msg = (f"PM2.5 {', '.join(res['months'])} — {res['records']:,}건 적재 완료 "
                       f"(측정소 {res['stations']}곳)")
                if res.get("skipped_stations"):
                    msg += f" · 미등록 역 제외: {', '.join(res['skipped_stations'])}"
                st.session_state["upload_msg"] = msg
                st.rerun()
            except RuntimeError as e:
                st.error(f"적재 실패: {e}")

    st.divider()
    st.markdown("### 적재된 데이터셋 목록")
    l1, l2 = st.columns(2)
    with l1:
        st.markdown("**통행량 (기준월별)**")
        if datasets["traffic"]:
            df_tr = pd.DataFrame(datasets["traffic"]).rename(
                columns={"period": "기준월", "records": "레코드 수", "stations": "역 수"})
            st.dataframe(df_tr, hide_index=True, use_container_width=True)
        else:
            st.caption("적재된 통행량 데이터가 없습니다.")
    with l2:
        st.markdown("**초미세먼지 (월별)**")
        if datasets["pm25"]:
            df_pm = pd.DataFrame(datasets["pm25"]).rename(
                columns={"month": "월", "records": "레코드 수", "stations": "측정소 수"})
            st.dataframe(df_pm, hide_index=True, use_container_width=True)
        else:
            st.caption("적재된 초미세먼지 데이터가 없습니다.")

# ============================================================
# 탭 5: 종합 리포트 (데이터 집계 기반 — LLM/추론 미사용)
# ============================================================
with tab5:
    rep = api_get("/api/report")
    st.subheader("종합 리포트")
    st.caption(
        f"생성 시각 {rep['generated_at']} · 모든 문장은 적재된 데이터의 집계값을 고정 템플릿에 대입해 "
        "생성한 것으로, LLM·추론을 사용하지 않은 통계적 사실 요약입니다."
    )

    r1, r2, r3, r4 = st.columns(4)
    if rep["pm25"]:
        r1.metric("PM2.5 전체 평균", f"{rep['pm25']['overall_avg']}㎍/㎥")
        r2.metric("환경기준(35) 초과율", f"{rep['pm25']['over35_ratio']}%")
    if rep["traffic"]:
        last_p = rep["traffic"]["per_period"][-1]
        delta = None
        if rep["traffic"]["period_change"]:
            delta = f"{rep['traffic']['period_change']['pct']:+.1f}%"
        r3.metric(f"통행량 ({last_p['period']})", f"{last_p['total']:,}명", delta=delta)
    if rep["cross"]:
        r4.metric("PM2.5×통행량 상관계수", f"{rep['cross']['correlation']:.2f}",
                   help="역별 PM2.5 평균 × 통행량 총량 (최신 기준월). 고정 구간표 분류.")

    st.markdown("#### 요약")
    for line in rep["findings"]:
        st.markdown(f"- {line}")

    d1, d2 = st.columns(2)
    with d1:
        if rep["pm25"]:
            st.markdown("**PM2.5 평균 상위 5개 역**")
            st.dataframe(pd.DataFrame(rep["pm25"]["top_stations"]).rename(
                columns={"station": "역", "avg": "평균(㎍/㎥)"}), hide_index=True, use_container_width=True)
            if len(rep["pm25"]["monthly"]) >= 2:
                st.markdown("**월별 PM2.5 평균 추이**")
                dfm = pd.DataFrame(rep["pm25"]["monthly"])
                figr = go.Figure(go.Bar(x=dfm["month"], y=dfm["avg"], marker_color="#2563eb"))
                figr.update_layout(height=200, yaxis_title="PM2.5 (㎍/㎥)", margin=dict(t=10))
                st.plotly_chart(figr, use_container_width=True)
    with d2:
        if rep["traffic"]:
            st.markdown(f"**통행량 상위 5개 역 ({rep['traffic']['per_period'][-1]['period']})**")
            st.dataframe(pd.DataFrame(rep["traffic"]["per_period"][-1]["top_stations"]).rename(
                columns={"station": "역", "total": "월 통행량(명)"}), hide_index=True, use_container_width=True)

    # 마크다운 리포트 다운로드
    md_lines = ["# 인천 1호선 초미세먼지·통행량 종합 리포트", f"생성: {rep['generated_at']}", ""]
    md_lines += [f"- {line}" for line in rep["findings"]]
    if rep["pm25"]:
        md_lines += ["", "## PM2.5 평균 상위 역"]
        md_lines += [f"- {d['station']}: {d['avg']}㎍/㎥" for d in rep["pm25"]["top_stations"]]
    if rep["traffic"]:
        md_lines += ["", f"## 통행량 상위 역 ({rep['traffic']['per_period'][-1]['period']})"]
        md_lines += [f"- {d['station']}: {d['total']:,}명" for d in rep["traffic"]["per_period"][-1]["top_stations"]]
    st.download_button("리포트 다운로드 (.md)", "\n".join(md_lines),
                        file_name="incheon_air_traffic_report.md", mime="text/markdown")
