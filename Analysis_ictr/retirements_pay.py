import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ----------------------------------------------------------------------
# 데이터 로드 및 전처리 (퇴사일 기준)
# ----------------------------------------------------------------------
@st.cache_data
def load_data(file_path):
    """
    '퇴직금_지급내역(20251025).csv' (5개 컬럼) 파일을 로드하고
    '퇴사일'을 기준으로 전처리합니다.
    """
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
        
        # --- [디버깅 1: 원본] ---
        with st.expander("DEBUG: 데이터 로드 과정 확인"):
            st.subheader("DEBUG: 1. 원본 CSV 로드 (head 5)")
            st.dataframe(df.head(5))
            st.subheader("DEBUG: 1-1. 원본 데이터 타입 (dtypes)")
            st.code(f"{df.dtypes}")

        # 1. YYYYMMDD 형식의 숫자(float/int)를 날짜로 변환
        df['퇴사일_str'] = df['퇴사일'].astype('Int64').astype(str)
        df['지급일_str'] = df['지급일'].astype('Int64').astype(str)
        df['입사일_str'] = df['입사일'].astype('Int64').astype(str)

        df['퇴사일_dt'] = pd.to_datetime(df['퇴사일_str'], format='%Y%m%d', errors='coerce')
        df['지급일_dt'] = pd.to_datetime(df['지급일_str'], format='%Y%m%d', errors='coerce')
        df['입사일_dt'] = pd.to_datetime(df['입사일_str'], format='%Y%m%d', errors='coerce')
        
        # 2. '퇴사년도', '퇴사월', '퇴사년월' (분석 기준) 파생 변수 생성
        df['퇴사년도'] = df['퇴사일_dt'].dt.year
        df['퇴사월'] = df['퇴사일_dt'].dt.month
        df['퇴사년월'] = df['퇴사일_dt'].dt.to_period('M').astype(str)
        
        # 3. '퇴직금' 컬럼(float64)을 '총지급액'으로 변환
        df['총지급액'] = df['퇴직금'] 

        # --- [디버깅 2: 변환 후] ---
        with st.expander("DEBUG: 데이터 로드 과정 확인"):
            st.subheader("DEBUG: 2. 전처리 후, 'dropna' 직전 (head 5)")
            st.dataframe(df.head(5))
            st.subheader("DEBUG: 2-1. 변환 후 결측치(NaN) 확인 (isna().sum())")
            check_cols = ['퇴사일', '퇴사일_str', '퇴사일_dt', '퇴사년도', '퇴직금', '총지급액']
            st.code(f"{df[check_cols].isna().sum()}")
            
        # 4. NaN 값이 있는 행 제거 (데이터 정합성)
        df = df.dropna(subset=['퇴사년도', '퇴사년월', '총지급액'])
        
        # 5. 년도와 월을 정수형으로 변환 (dropna 이후에 수행해야 안전)
        df = df.copy() 
        df['퇴사년도'] = df['퇴사년도'].astype(int)
        df['퇴사월'] = df['퇴사월'].astype(int)
        
        # --- [디버깅 3: 최종] ---
        with st.expander("DEBUG: 데이터 로드 과정 확인"):
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
# 메인 대시보드 UI
# ----------------------------------------------------------------------
st.title("📊 퇴직금 지급 현황 (퇴사일 기준)")
st.markdown("---")

# --- 데이터 로드 ---
file_path_pay = '퇴직금_지급내역(20251025).csv'
df_pay = load_data(file_path_pay)

if not df_pay.empty:
    
    # --- 1. 핵심 지표 (KPIs) ---
    st.subheader("📊 지급 현황 요약")
    total_payment_sum = df_pay['총지급액'].sum()
    total_retirees_count = len(df_pay)
    avg_payment = 0 if total_retirees_count == 0 else total_payment_sum / total_retirees_count
    
    # '백만원' 단위로 변환
    total_payment_mil = total_payment_sum / 1_000_000
    avg_payment_mil = avg_payment / 1_000_000

    cols = st.columns(3)
    
    # --- [수정된 부분: st.metric을 st.markdown(HTML)으로 변경] ---
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

    with cols[0]:
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

    with cols[1]:
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
    
    with cols[2]:
        # 총 퇴직자 수는 기존 st.metric 유지 (단위가 없으므로)
        st.metric(label="총 퇴직자 수", value=f"{total_retirees_count:,} 명")
    
    st.markdown("<br>", unsafe_allow_html=True) # 줄바꿈
    st.markdown("---")
    # --- [수정 끝] ---

    # --- 2. 년도별 퇴직금 지급 현황 (Bar Chart) ---
    st.subheader("📈 년도별 퇴직금 지급 현황")
    
    df_yearly = df_pay.groupby('퇴사년도')['총지급액'].sum().reset_index()
    df_yearly['총지급액_백만원'] = df_yearly['총지급액'] / 1_000_000
    
    fig_yearly = px.bar(
        df_yearly, 
        x='퇴사년도', 
        y='총지급액_백만원', # Y축 변경
        title='퇴사 년도별 총 지급액'
        # text_auto 제거 -> update_traces에서 설정
    )
    
    # --- [수정된 부분: texttemplate으로 가독성 확보] ---
    # texttemplate: 막대 위에 표시될 텍스트 서식 (쉼표 O, 소수점 X)
    # textposition: 'outside' (막대 바깥쪽 상단)
    fig_yearly.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
    fig_yearly.update_xaxes(type='category')
    fig_yearly.update_layout(
        yaxis_title="총 지급액 (백만원)"
    )
    # --- [수정 끝] ---
    
    st.plotly_chart(fig_yearly, use_container_width=True)
    st.markdown("---")
    
    # --- 3. 월별 퇴직금 지급 및 누계 현황 (Dual Axis Chart) ---
    st.subheader("📊 월별 퇴직금 지급 및 누계 현황")
    
    # 년월별 집계
    df_monthly = df_pay.groupby('퇴사년월')['총지급액'].sum().reset_index()
    df_monthly = df_monthly.sort_values(by='퇴사년월')
    
    df_monthly['총지급액_백만원'] = df_monthly['총지급액'] / 1_000_000
    df_monthly['누적 지급액_백만원'] = df_monthly['총지급액_백만원'].cumsum()
    
    # 이중 축 차트 생성
    fig_dual = go.Figure()

    # 막대 차트: 월별 퇴직금 (증가량)
    fig_dual.add_trace(go.Bar(
        x=df_monthly['퇴사년월'],
        y=df_monthly['총지급액_백만원'], # Y축 변경
        name='월별 총지급액 (백만원)',
        marker_color='blue',
        # --- [수정] 툴팁 서식 (소수점 X) ---
        hovertemplate='<b>%{x}</b><br>월별 지급액: %{y:,.0f} 백만원<extra></extra>'
    ))

    # 라인 차트: 퇴직금 누계
    fig_dual.add_trace(go.Scatter(
        x=df_monthly['퇴사년월'],
        y=df_monthly['누적 지급액_백만원'], # Y축 변경
        name='누적 지급액 (백만원)',
        mode='lines+markers',
        marker_color='red',
        yaxis='y2', # 두 번째 Y축 사용
        # --- [수정] 툴팁 서식 (소수점 X) ---
        hovertemplate='<b>%{x}</b><br>누적 지급액: %{y:,.0f} 백만원<extra></extra>'
    ))

    # --- [수정] Y축 레이블/서식 변경 ---
    fig_dual.update_layout(
        title='퇴사 월별 퇴직금 지급액 및 누계 추이',
        xaxis_title='퇴사 년월',
        yaxis=dict(
            title='월별 총지급액 (백만원)', # 레이블 변경
            color='blue'
        ),
        yaxis2=dict(
            title='누적 지급액 (백만원)', # 레이블 변경
            color='red',
            overlaying='y',
            side='right'
        ),
        legend=dict(x=0.01, y=0.99)
    )
    # --- [수정 끝] ---
    
    st.plotly_chart(fig_dual, use_container_width=True)

else:
    st.error(f"'{file_path_pay}' 파일을 로드하지 못했거나 데이터가 비어있습니다. DEBUG 창에서 컬럼명과 결측치를 확인하세요.")