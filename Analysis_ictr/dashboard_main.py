import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ----------------------------------------------------------------------
# 페이지 기본 설정
# ----------------------------------------------------------------------
st.set_page_config(layout="wide")

# ----------------------------------------------------------------------
# 데이터 로드 함수 1: 과거 지급 내역 (retirements_pay.py 최종 로직 적용)
# ----------------------------------------------------------------------
@st.cache_data
def load_payment_data(file_path):
    """
    '퇴직금_지급내역(20251025).csv' (5개 컬럼) 파일을 로드하고
    Tab1(지급일 기준)과 Tab2(퇴사일 기준)에 필요한 모든 컬럼을 전처리합니다.
    """
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
        
        # --- [디버깅 1: 원본] ---
        with st.expander("DEBUG: '과거 지급 내역' 데이터 로드 과정 확인"):
            st.subheader("DEBUG: 1. 원본 CSV 로드 (head 5)")
            st.dataframe(df.head(5))
            st.subheader("DEBUG: 1-1. 원본 데이터 타입 (dtypes)")
            st.code(f"{df.dtypes}")

        # --- [수정된 부분 시작] ---
        
        # 1. (가설) 날짜 컬럼(float/int)이 YYYYMMDD 형식의 숫자입니다.
        #    먼저 Nullable 정수(Int64)로 변환하여 '.0'을 제거하고,
        #    그 다음 문자(str)로 변환합니다.
        df['퇴사일_str'] = df['퇴사일'].astype('Int64').astype(str)
        df['지급일_str'] = df['지급일'].astype('Int64').astype(str)
        df['입사일_str'] = df['입사일'].astype('Int64').astype(str)

        # 2. YYYYMMDD 형식의 문자열을 datetime 객체로 변환합니다.
        df['퇴사일_dt'] = pd.to_datetime(df['퇴사일_str'], format='%Y%m%d', errors='coerce')
        df['지급일_dt'] = pd.to_datetime(df['지급일_str'], format='%Y%m%d', errors='coerce')
        df['입사일_dt'] = pd.to_datetime(df['입사일_str'], format='%Y%m%d', errors='coerce')
        
        # 3. '퇴사년도', '퇴사월', '퇴사년월' (Tab 2 분석 기준) 파생 변수 생성
        df['퇴사년도'] = df['퇴사일_dt'].dt.year
        df['퇴사월'] = df['퇴사일_dt'].dt.month
        df['퇴사년월'] = df['퇴사일_dt'].dt.to_period('M').astype(str)
        
        # 4. '지급년도', '지급월' (Tab 1 분석 기준) 파생 변수 생성
        df['지급년도'] = df['지급일_dt'].dt.year
        df['지급월'] = df['지급일_dt'].dt.month
        
        # 5. '퇴직금' 컬럼(float64)을 '총지급액'으로 변환 (쉼표 제거 로직 불필요)
        df['총지급액'] = df['퇴직금'] 

        # --- [디버깅 2: 변환 후] ---
        with st.expander("DEBUG: '과거 지급 내역' 데이터 로드 과정 확인"):
            st.subheader("DEBUG: 2. 전처리 후, 'dropna' 직전 (head 5)")
            st.dataframe(df.head(5))
            st.subheader("DEBUG: 2-1. 변환 후 결측치(NaN) 확인 (isna().sum())")
            # 모든 핵심 컬럼 확인
            check_cols = ['퇴사일_dt', '퇴사년도', '지급일_dt', '지급년도', '총지급액']
            st.code(f"{df[check_cols].isna().sum()}")
            
        # 6. [수정] NaN 값이 있는 행 제거 (데이터 정합성)
        #    Tab1과 Tab2 분석에 필요한 핵심 컬럼 기준
        df = df.dropna(subset=['퇴사일_dt', '지급일_dt', '총지급액'])
        
        # 7. 년도와 월을 정수형으로 변환 (dropna 이후에 수행해야 안전)
        df = df.copy() 
        df['퇴사년도'] = df['퇴사년도'].astype(int)
        df['퇴사월'] = df['퇴사월'].astype(int)
        df['지급년도'] = df['지급년도'].astype(int)
        df['지급월'] = df['지급월'].astype(int)
        
        # --- [수정된 부분 끝] ---
        
        # --- [디버깅 3: 최종] ---
        with st.expander("DEBUG: '과거 지급 내역' 데이터 로드 과정 확인"):
            st.subheader("DEBUG: 3. 최종 전처리 완료 (head 5)")
            st.dataframe(df.head(5))
            if df.empty:
                st.error("DEBUG: 3-1. 'dropna' 이후 데이터가 비어있습니다. 'DEBUG 2-1'을 확인하세요.")
        
        return df
        
    except FileNotFoundError:
        st.error(f"'{file_path}' 파일을 찾을 수 없습니다. 경로를 확인하세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"'과거 지급 내역' 처리 중 오류: {e}. CSV 파일에 '사번', '지급일', '입사일', '퇴사일', '퇴직금' 컬럼이 있는지 확인하세요.") 
        return pd.DataFrame()

# ----------------------------------------------------------------------
# 데이터 로드 함수 2: 미래 퇴직 추계 (retirements_rate.py 기반)
# ----------------------------------------------------------------------
@st.cache_data
def load_retirement_data(file_path):
    """미래 퇴직 예정자 데이터를 로드하고 전처리합니다."""
    try:
        df = pd.read_csv(file_path, encoding='utf-8')

        # 생년월일 변환 (integer 6자리 -> 8자리 string -> datetime)
        birth_str = df['생년월일'].astype(str)
        birth_full_str = '19' + birth_str # 19xx년생으로 가정
        df['생년월일'] = pd.to_datetime(birth_full_str, format='%Y%m%d', errors='coerce')
        
        df = df.dropna(subset=['생년월일'])  # 변환 실패(NaT) 데이터 제거

        # 현재 연도 및 나이 계산
        current_year = pd.Timestamp.now().year
        df['나이'] = current_year - df['생년월일'].dt.year

        # 예상 퇴직 연도 계산 (60세 정년 기준)
        df['예상퇴직연도'] = df['생년월일'].dt.year + 60

        # 필터링: 2026년도부터 퇴직 예정자 중 67년생 이상만 선택
        df_filtered = df[(df['예상퇴직연도'] >= 2026) & (df['생년월일'].dt.year >= 1967)]
        
        return df_filtered

    except FileNotFoundError:
        st.error(f"'{file_path}' 파일을 찾을 수 없습니다. 경로를 확인하세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"'미래 퇴직 추계' 처리 중 오류: {e}")
        return pd.DataFrame()

# ----------------------------------------------------------------------
# 메인 대시보드 UI
# ----------------------------------------------------------------------
st.title("📊 통합 퇴직금 대시보드 (과거 분석 및 미래 추계)")
st.markdown("---")

# --- 데이터 로드 ---
file_path_pay = '퇴직금_지급내역(20251025).csv'
file_path_rate = '퇴직예정자(65_80).csv'

df_pay = load_payment_data(file_path_pay)
df_rate = load_retirement_data(file_path_rate)

# --- 탭(Tab) 생성 ---
tab1, tab2, tab3 = st.tabs(["🏠 종합 현황", "💰 과거 지급 분석", "👥 미래 퇴직 추계"])


# ----------------------------------------------------------------------
# 탭 1: 🏠 종합 현황 (Executive Summary)
# ----------------------------------------------------------------------
with tab1:
    st.header("🏠 종합 현황 요약")
    
    # 데이터 로드 성공 여부 확인
    data_loaded_ok = not df_pay.empty and not df_rate.empty
    
    if data_loaded_ok:
        # --- 1-1. 핵심 지표 (KPIs) ---
        st.subheader("📊 핵심 지표 (KPI)")
        cols1 = st.columns(4)
        
        # 과거 지표 (df_pay 로드 성공)
        total_payment_sum = df_pay['총지급액'].sum()
        total_retirees_count = len(df_pay)
        avg_payment = 0 if total_retirees_count == 0 else total_payment_sum / total_retirees_count
        
        # 미래 지표
        total_future_retirees = len(df_rate)
        
        cols1[0].metric(label="과거 총 지급액", value=f"{total_payment_sum/1_0000_0000:.1f} 억원")
        cols1[1].metric(label="과거 1인당 평균 지급액", value=f"{avg_payment/1_0000:.1f} 만원")
        cols1[2].metric(label="과거 총 퇴직자 수", value=f"{total_retirees_count:,} 명")
        cols1[3].metric(label="미래 예상 퇴직자 수 (필터 기준)", value=f"{total_future_retirees:,} 명")
        
        st.markdown("---")
        
        # --- 1-2. 핵심 통합 차트 (과거 vs 미래) ---
        st.subheader("📈 과거 지급액 vs. 미래 예상 퇴직자")
        st.info("과거 년도별 '총 지급액(라인)'과 미래 년도별 '예상 퇴직자 수(막대)'를 한눈에 비교합니다.")

        # 1. 과거 데이터 집계 (지급년도 기준)
        df_pay_yearly = df_pay.groupby('지급년도')['총지급액'].sum().reset_index()
        
        # 2. 미래 데이터 집계
        df_rate_yearly = df_rate.groupby('예상퇴직연도').size().reset_index(name='예상 퇴직자 수')

        # 3. 이중 Y축(Dual-Axis) 차트 생성
        fig_combined = make_subplots(specs=[[{"secondary_y": True}]])

        # Trace 1: 과거 총 지급액 (라인, Y축1)
        fig_combined.add_trace(
            go.Scatter(
                x=df_pay_yearly['지급년도'],
                y=df_pay_yearly['총지급액'],
                name="과거 총 지급액 (원)",
                mode='lines+markers',
                yaxis='y1' # Y축1 명시
            ),
            secondary_y=False,
        )
        
        # Trace 2: 미래 예상 퇴직자 (막대, Y축2)
        fig_combined.add_trace(
            go.Bar(
                x=df_rate_yearly['예상퇴직연도'],
                y=df_rate_yearly['예상 퇴직자 수'],
                name="미래 예상 퇴직자 (명)",
                opacity=0.7,
                yaxis='y2' # Y축2 명시
            ),
            secondary_y=True,
        )

        # 레이아웃 및 축 제목 설정
        fig_combined.update_layout(
            title_text="과거 지급 현황 vs. 미래 퇴직 추계",
            xaxis_title="년도"
        )
        fig_combined.update_xaxes(type='category') 
        # [수정] Y축 서식 변경 (쉼표)
        fig_combined.update_yaxes(
            title_text="💰 총 지급액 (원)", 
            tickformat=',', # 쉼표 서식
            secondary_y=False
        )
        fig_combined.update_yaxes(
            title_text="👥 예상 퇴직자 (명)", 
            secondary_y=True
        )
        
        st.plotly_chart(fig_combined, use_container_width=True)

    else:
        st.warning("데이터 파일 로드에 실패하여 종합 현황을 표시할 수 없습니다. (적어도 하나의 파일이 로드되지 않았습니다.)")


# ----------------------------------------------------------------------
# 탭 2: 💰 과거 지급 분석 (retirements_pay.py 최종 로직)
# ----------------------------------------------------------------------
with tab2:
    st.header("💰 과거 퇴직금 지급 상세 분석 (퇴사일 기준)")

    if not df_pay.empty:
        # --- 2-1. 핵심 지표 (KPIs) - '백만원' 단위, HTML/CSS 적용 ---
        st.subheader("📊 지급 현황 요약")
        total_payment_sum = df_pay['총지급액'].sum()
        total_retirees_count = len(df_pay)
        avg_payment = 0 if total_retirees_count == 0 else total_payment_sum / total_retirees_count
        
        total_payment_mil = total_payment_sum / 1_000_000
        avg_payment_mil = avg_payment / 1_000_000

        cols2 = st.columns(3)
        
        # CSS를 이용해 숫자와 단위의 글씨 크기를 다르게 설정
        metric_style = """
            <style>
                .metric-container {
                    border: 1px solid #333;
                    border-radius: 10px;
                    padding: 10px;
                    text-align: left;
                }
                .metric-label {
                    font-size: 1rem;
                    color: #888;
                    margin-bottom: 5px;
                }
                .metric-value {
                    font-size: 2rem;
                    font-weight: bold;
                }
                .metric-unit {
                    font-size: 1.2rem; /* '백만원' 글씨 크기 */
                    color: #888;
                    margin-left: 8px; 
                }
            </style>
        """
        st.markdown(metric_style, unsafe_allow_html=True)

        with cols2[0]:
            st.markdown(
                f"""
                <div class="metric-container">
                    <div class="metric-label">총 지급액</div>
                    <div>
                        <span class="metric-value">{total_payment_mil:,.0f}</span>
                        <span class="metric-unit">백만원</span>
                    </div>
                </div>
                """, unsafe_allow_html=True
            )

        with cols2[1]:
            st.markdown(
                f"""
                <div class="metric-container">
                    <div class="metric-label">1인당 평균 지급액</div>
                    <div>
                        <span class="metric-value">{avg_payment_mil:,.0f}</span>
                        <span class="metric-unit">백만원</span>
                    </div>
                </div>
                """, unsafe_allow_html=True
            )
        
        with cols2[2]:
            st.metric(label="총 퇴직자 수", value=f"{total_retirees_count:,} 명")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("---")
        # --- 2-1 끝 ---

        # --- 2-2. 년도별 퇴직금 지급 현황 (퇴사년도 기준) ---
        st.subheader("📈 년도별 퇴직금 지급 현황")
        
        # '퇴사년도' 기준 집계
        df_yearly = df_pay.groupby('퇴사년도')['총지급액'].sum().reset_index()
        df_yearly['총지급액_백만원'] = df_yearly['총지급액'] / 1_000_000
        
        fig_yearly = px.bar(
            df_yearly, 
            x='퇴사년도', 
            y='총지급액_백만원',
            title='퇴사 년도별 총 지급액'
        )
        
        # 텍스트 서식: 쉼표 O, 소수점 X
        fig_yearly.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
        fig_yearly.update_xaxes(type='category')
        fig_yearly.update_layout(
            yaxis_title="총 지급액 (백만원)"
        )
        
        st.plotly_chart(fig_yearly, use_container_width=True)
        st.markdown("---")
        
        # --- 2-3. 월별 퇴직금 지급 및 누계 현황 (퇴사년월 기준) ---
        st.subheader("📊 월별 퇴직금 지급 및 누계 현황")
        
        # '퇴사년월' 기준 집계
        df_monthly = df_pay.groupby('퇴사년월')['총지급액'].sum().reset_index()
        df_monthly = df_monthly.sort_values(by='퇴사년월')
        
        df_monthly['총지급액_백만원'] = df_monthly['총지급액'] / 1_000_000
        df_monthly['누적 지급액_백만원'] = df_monthly['총지급액_백만원'].cumsum()
        
        fig_dual = go.Figure()

        # 막대 차트
        fig_dual.add_trace(go.Bar(
            x=df_monthly['퇴사년월'],
            y=df_monthly['총지급액_백만원'], 
            name='월별 총지급액 (백만원)',
            marker_color='blue',
            hovertemplate='<b>%{x}</b><br>월별 지급액: %{y:,.0f} 백만원<extra></extra>'
        ))

        # 라인 차트
        fig_dual.add_trace(go.Scatter(
            x=df_monthly['퇴사년월'],
            y=df_monthly['누적 지급액_백만원'], 
            name='누적 지급액 (백만원)',
            mode='lines+markers',
            marker_color='red',
            yaxis='y2',
            hovertemplate='<b>%{x}</b><br>누적 지급액: %{y:,.0f} 백만원<extra></extra>'
        ))

        # 레이아웃 설정
        fig_dual.update_layout(
            title='퇴사 월별 퇴직금 지급액 및 누계 추이',
            xaxis_title='퇴사 년월',
            yaxis=dict(
                title='월별 총지급액 (백만원)',
                color='blue'
            ),
            yaxis2=dict(
                title='누적 지급액 (백만원)',
                color='red',
                overlaying='y',
                side='right'
            ),
            legend=dict(x=0.01, y=0.99)
        )
        st.plotly_chart(fig_dual, use_container_width=True)

    else:
        st.error(f"'{file_path_pay}' 파일을 로드하지 못했거나 데이터가 비어있습니다. DEBUG 창에서 컬럼명과 결측치를 확인하세요.")


# ----------------------------------------------------------------------
# 탭 3: 👥 미래 퇴직 추계 (retirements_rate.py 내용)
# ----------------------------------------------------------------------
with tab3:
    st.header("👥 미래 예상 퇴직자 상세 분석")
    st.markdown("*(분석 기준: 2026년 이후 퇴직자, 1967년생 이상)*")

    if not df_rate.empty:
        # --- 3-1. 미래 KPI ---
        st.subheader("👥 예상 퇴직자 수")
        total_future_retirees = len(df_rate)
        st.metric(label="예상 퇴직자 수 (필터 기준)", value=f"{total_future_retirees:,}명")
        
        st.markdown("---")

        # --- 3-2. 년도별, 직군별 분석 ---
        st.subheader("🗓️ 년도별, 직군별 예상 퇴직자 분석")

        # 데이터 집계 (수)
        df_agg = df_rate.groupby(['예상퇴직연도', '직군']).size().reset_index(name='퇴직자 수')
        
        # 비율 계산
        total_per_year = df_agg.groupby('예상퇴직연도')['퇴직자 수'].transform('sum')
        
        # [수정] 오타 수정 ('_퇴직자 수' -> '퇴직자 수')
        df_agg['비율 (%)'] = (df_agg['퇴직자 수'] / total_per_year) * 100

        # 데이터 테이블 (피벗)
        st.info("데이터 표: 직군별, 년도별 예상 퇴직자 수")
        df_pivot = df_agg.pivot_table(index='직군', columns='예상퇴직연도', values='퇴직자 수', fill_value=0)
        st.dataframe(df_pivot)

        # 차트 1: 퇴직자 수 (누적 막대)
        st.info("차트 1: 년도별 총 퇴직자 수 및 직군별 구성 (단위: 명)")
        fig_yearly_job_count = px.bar(
            df_agg,
            x='예상퇴직연도',
            y='퇴직자 수',
            color='직군',
            title='년도별/직군별 예상 퇴직자 수',
            text_auto=True
        )
        fig_yearly_job_count.update_xaxes(type='category')
        st.plotly_chart(fig_yearly_job_count, use_container_width=True)

        # 차트 2: 퇴직자 비율 (100% 누적 막대)
        st.info("차트 2: 년도별 직군 구성 비율 (100% 누적)")
        fig_yearly_job_ratio = px.bar(
            df_agg,
            x='예상퇴직연도',
            y='비율 (%)',
            color='직군',
            title='년도별/직군별 예상 퇴직자 비율 (100% 누적)',
            text=df_agg['비율 (%)'].map(lambda x: f"{x:.1f}%") # 비율은 소수점 표시
        )
        fig_yearly_job_ratio.update_traces(textposition='inside')
        fig_yearly_job_ratio.update_xaxes(type='category')
        st.plotly_chart(fig_yearly_job_ratio, use_container_width=True)

    else:
        st.error(f"'{file_path_rate}' 파일을 로드하지 못했거나 필터 조건에 맞는 데이터가 없습니다.")