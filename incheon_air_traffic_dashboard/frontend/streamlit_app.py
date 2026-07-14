"""인천 1호선 초미세먼지 · 통행량 통합 분석 대시보드 (Streamlit 프론트엔드)

백엔드(FastAPI + PostgreSQL)에서 데이터를 받아
과제1(추세·예측) / 과제2(교차분석) / 과제3(지도) 3개 탭으로 시각화한다.
"""
import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from app_common import get_stations, pm25_stations, api_get

st.set_page_config(page_title="인천 1호선 초미세먼지·통행량 대시보드", layout="wide")

st.title("인천 1호선 초미세먼지 · 통행량 통합 분석 대시보드")
st.caption(
    "초미세먼지(PM2.5) 시간대별 월보 · 역·시간대별 통행량 · 역사 위치 기반 통합 시각화"
)

try:
    stations = get_stations()
except Exception as e:
    st.error(f"백엔드 API({e.__class__.__name__})에 연결할 수 없습니다. backend 서비스가 기동 중인지 확인하세요.")
    st.stop()

pm_stations = pm25_stations(stations)

tab1, tab2, tab3 = st.tabs(["1. 추세 · 기간예측", "2. 미세먼지-통행량 교차분석", "3. 혼잡도-미세먼지 지도"])

# ============================================================
# 탭 1: 추세 · 기간예측
# ============================================================
with tab1:
    st.subheader("과제1. 역사별 시간대별 초미세먼지 추세 · 기간예측")
    c1, c2, c3, c4, c5 = st.columns(5)
    station = c1.selectbox("측정소(역)", pm_stations, index=pm_stations.index("부평") if "부평" in pm_stations else 0)
    start_day = c2.number_input("시작일(10월)", min_value=1, max_value=31, value=1)
    end_day = c3.number_input("종료일(10월)", min_value=1, max_value=31, value=31)
    model = c4.selectbox("예측 모델", ["seasonal", "linear"],
                          format_func=lambda v: "계절성 분해(요일×시간대 패턴)" if v == "seasonal" else "선형회귀 / 추세선")
    horizon = c5.selectbox("예측 기간", [3, 7, 14], index=1, format_func=lambda v: f"향후 {v}일")

    if start_day > end_day:
        st.warning("시작일은 종료일보다 작거나 같아야 합니다.")
    else:
        data = api_get("/api/trend/forecast", {
            "station": station, "start_day": start_day, "end_day": end_day,
            "model": model, "horizon_days": horizon,
        })
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
        fig.update_layout(height=420, xaxis_title="시간", yaxis_title="PM2.5 (㎍/㎥)",
                           legend=dict(orientation="h", y=1.08), margin=dict(t=30))
        fig.update_xaxes(tickmode="auto", nticks=14)
        st.plotly_chart(fig, use_container_width=True)

    st.caption("데이터: 2024년 10월 초미세먼지 월보(1시간 평균, 28개 측정소). 예측은 과거 패턴 기반 통계적 추정입니다.")

# ============================================================
# 탭 2: 미세먼지-통행량 교차분석
# ============================================================
with tab2:
    st.subheader("과제2. 초미세먼지 × 역 통행량 교차분석")
    st.warning(
        "⚠ 두 자료의 수집 시기가 다릅니다 — 초미세먼지: 2024년 10월(0시~24시 1시간 단위) / "
        "통행량: 2026년 4월(05시~24시 이후 20구간). 따라서 절대 시점 비교가 아닌 **하루 중 시간대별 평균 패턴** "
        "간의 교차 비교이며, 초미세먼지의 0시대 데이터를 통행량의 '24시이후' 구간에 대응시켰습니다."
    )
    station2 = st.selectbox("역 선택(공통 28개 역)", pm_stations, key="station2",
                             index=pm_stations.index("부평") if "부평" in pm_stations else 0)

    cc1, cc2 = st.columns([1.3, 1])
    with cc1:
        cross = api_get(f"/api/cross/{station2}")
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=cross["hour_labels"], y=cross["traffic_total"],
                               name="통행량(승차+하차)", marker_color="rgba(37,99,235,.5)", yaxis="y"))
        fig2.add_trace(go.Scatter(x=cross["hour_labels"], y=cross["pm_aligned"], name="PM2.5 평균(㎍/㎥)",
                                   mode="lines+markers", line=dict(color="#f97316", width=2), yaxis="y2"))
        fig2.update_layout(
            height=380,
            yaxis=dict(title="통행량(명)"),
            yaxis2=dict(title="PM2.5(㎍/㎥)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1), margin=dict(t=30),
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.metric(f"{station2} 시간대 패턴 상관계수", f"{cross['correlation']*100:.1f}%")

    with cc2:
        scatter = api_get("/api/cross/")
        df = pd.DataFrame(scatter["points"])
        df["highlight"] = df["station"].apply(lambda s: "선택역" if s == station2 else "기타 역")
        fig3 = go.Figure()
        for grp, color, size in [("기타 역", "rgba(37,99,235,.55)", 8), ("선택역", "#dc2626", 13)]:
            sub = df[df["highlight"] == grp]
            fig3.add_trace(go.Scatter(x=sub["avg_pm25"], y=sub["total_traffic"], mode="markers",
                                       name=grp, marker=dict(color=color, size=size),
                                       text=sub["station"], hovertemplate="%{text}<br>PM2.5 %{x:.1f}<br>통행량 %{y:,}"))
        fig3.update_layout(height=380, xaxis_title="PM2.5 월평균(㎍/㎥)", yaxis_title="일 통행량 합계(명)",
                            legend=dict(orientation="h", y=1.1), margin=dict(t=30))
        st.plotly_chart(fig3, use_container_width=True)
        st.metric("전체 28개 역 기준 상관계수", f"{scatter['correlation']*100:.1f}%")

# ============================================================
# 탭 3: 혼잡도-미세먼지 지도
# ============================================================
with tab3:
    st.subheader("과제3. 역사 위치 기반 혼잡도-미세먼지 상관관계 지도")
    st.info(
        "위치 좌표: 인천교통공사 공식 역정보(도로명주소) 및 공개 지리정보 기반 근사좌표입니다. "
        "원(마커) 크기 = 일 통행량(승차+하차 합), 색상 = 2024년 10월 PM2.5 월평균 "
        "(회색 = 미세먼지 측정소 없음: 검단호수공원·신검단중앙·아라·계양·귤현)."
    )
    mapdata = api_get("/api/map")
    df_map = pd.DataFrame(mapdata["points"])

    m1, m2 = st.columns([1.4, 1])
    with m1:
        fmap = folium.Map(location=[37.48, 126.70], zoom_start=11, tiles="OpenStreetMap")
        # df_map은 /api/map 응답 순서(노선순서, line_order 기준)를 그대로 유지하므로 바로 폴리라인으로 연결 가능
        folium.PolyLine(list(zip(df_map["lat"], df_map["lon"])), color="#94a3b8", weight=3, opacity=.6).add_to(fmap)

        max_cong = df_map["congestion"].max() or 1

        def pm_color(v):
            if v is None:
                return "#94a3b8"
            if v < 15: return "#22c55e"
            if v < 25: return "#84cc16"
            if v < 35: return "#eab308"
            if v < 50: return "#f97316"
            return "#dc2626"

        for _, row in df_map.iterrows():
            radius = 5 + 14 * ((row["congestion"] or 0) / max_cong) ** 0.5
            popup = (f"<b>{row['station']}</b><br>"
                     f"월평균 PM2.5: {'%.1f㎍/㎥' % row['avg_pm25'] if pd.notnull(row['avg_pm25']) else '측정소 없음'}<br>"
                     f"일 통행량(승하차합): {int(row['congestion']):,}명" if pd.notnull(row['congestion']) else "-")
            folium.CircleMarker(
                location=[row["lat"], row["lon"]], radius=radius,
                color="#1e293b", weight=1, fill=True, fill_opacity=.8,
                fill_color=pm_color(row["avg_pm25"]), popup=popup,
            ).add_to(fmap)
        st_folium(fmap, height=520, use_container_width=True)

    with m2:
        st.metric("통행량-PM2.5 상관계수(28개 역)", f"{mapdata['correlation']*100:.1f}%")
        st.markdown(
            "🟢 <15 &nbsp; 🟡 15-25 &nbsp; 🟠 25-35 &nbsp; 🔴 35-50 &nbsp; 🟥 ≥50 ㎍/㎥",
            unsafe_allow_html=True,
        )
        st.markdown("**통행량 상위 5개 역**")
        for p in mapdata["top_congestion"]:
            st.write(f"- {p['station']} — {p['congestion']:,}명/일, PM2.5 {p['avg_pm25']:.1f}")
        st.markdown("**PM2.5 상위 5개 역**")
        for p in mapdata["top_pm25"]:
            st.write(f"- {p['station']} — PM2.5 {p['avg_pm25']:.1f}㎍/㎥, 통행량 {p['congestion']:,}명/일")
