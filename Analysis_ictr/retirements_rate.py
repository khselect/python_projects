import streamlit as st
import pandas as pd
import plotly.express as px

# --- 데이터 로드 및 전처리 ---
@st.cache_data
def load_retirement_data(file_path):
    """퇴직 예정자 데이터를 로드하고 전처리합니다."""
    try:
        # CSV 파일 로드
        df = pd.read_csv(file_path, encoding='utf-8')

        # --- [수정된 부분] ---
        # 생년월일 변환 (integer 6자리 -> 8자리 string -> datetime)
        birth_str = df['생년월일'].astype(str)
        birth_full_str = '19' + birth_str
        df['생년월일'] = pd.to_datetime(birth_full_str, format='%Y%m%d', errors='coerce')
        
        df = df.dropna(subset=['생년월일'])  # 변환 실패(NaT) 데이터 제거

        # 현재 연도 및 나이 계산
        current_year = pd.Timestamp.now().year
        df['나이'] = current_year - df['생년월일'].dt.year

        # 예상 퇴직 연도 계산 (60세 정년 기준)
        df['예상퇴직연도'] = df['생년월일'].dt.year + 60

        # 필터링: 2026년도부터 퇴직 예정자 중 67년생 이상만 선택
        df_filtered = df[(df['예상퇴직연도'] >= 2026) & (df['생년월일'].dt.year >= 1967)]
        
        st.write("최종 필터링된 데이터 수:", len(df_filtered))

        return df_filtered

    except FileNotFoundError:
        st.error(f"'{file_path}' 파일을 찾을 수 없습니다. 경로를 확인하세요.")
        return pd.DataFrame()

    except Exception as e:
        st.error(f"데이터를 처리하는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

# --- 데이터 로드 ---
file_path = '퇴직예정자(65_80).csv'
df_retirement = load_retirement_data(file_path)

# 데이터 로드 후 확인
st.write("데이터 샘플:", df_retirement.head())
st.write("생년월일 데이터 타입:", df_retirement['생년월일'].dtype)

# --- 대시보드 UI 구성 ---
st.title("📊 2026년도 이후 예상 퇴직자 분석 대시보드")
st.markdown("---")

if not df_retirement.empty:
    # 1. 예상 퇴직자 수 (필터링된 기준)
    st.header("👥 예상 퇴직자 수")
    total_retirees = len(df_retirement)
    st.metric(label="예상 퇴직자 수 (2026년 이후, 67년생 이상)", value=f"{total_retirees:,}명")
    st.markdown("---")
    
    # --- [삭제] ---
    # 2. 부서별 퇴직자 비율 (이 섹션 전체 삭제)
    
    # --- [수정 및 추가] ---
    # 3. 년도별, 직군별 퇴직자 분석
    st.header("🗓️ 년도별, 직군별 예상 퇴직자 분석")

    # 3-1. 데이터 집계 (수)
    df_agg = df_retirement.groupby(['예상퇴직연도', '직군']).size().reset_index(name='퇴직자 수')
    
    # 3-2. 비율 계산
    # 년도별 합계
    total_per_year = df_agg.groupby('예상퇴직연도')['퇴직자 수'].transform('sum')
    # 년도 내 직군별 비율
    df_agg['비율 (%)'] = (df_agg['퇴직자 수'] / total_per_year) * 100

    # 3-3. 데이터 테이블 (수와 비율 표시)
    st.subheader("📊 예상 퇴직자 수 (표)")
    st.info("데이터 표: 직군별, 년도별 예상 퇴직자 수")
    df_pivot = df_agg.pivot_table(index='직군', columns='예상퇴직연도', values='퇴직자 수', fill_value=0)
    st.dataframe(df_pivot)

    # 3-4. 시각화 (차트 - 퇴직자 수)
    st.subheader("📈 예상 퇴직자 수 (년도별/직군별)")
    st.info("차트 1: 년도별 총 퇴직자 수 및 직군별 구성 (단위: 명)")
    fig_yearly_job_count = px.bar(
        df_agg,
        x='예상퇴직연도',
        y='퇴직자 수',
        color='직군',
        title='년도별/직군별 예상 퇴직자 수',
        text_auto=True # 막대 위에 값(수) 표시
    )
    # X축을 범주형으로 설정하여 모든 년도가 표시되도록 함
    fig_yearly_job_count.update_xaxes(type='category')
    st.plotly_chart(fig_yearly_job_count, use_container_width=True)

    # 3-5. 시각화 (차트 - 비율)
    st.subheader("📈 예상 퇴직자 비율 (년도별/직군별)")
    st.info("차트 2: 년도별 직군 구성 비율 (100% 누적)")
    fig_yearly_job_ratio = px.bar(
        df_agg,
        x='예상퇴직연도',
        y='비율 (%)',
        color='직군',
        title='년도별/직군별 예상 퇴직자 비율 (100% 누적)',
        text=df_agg['비율 (%)'].map(lambda x: f"{x:.1f}%") # 막대 위에 값(비율) 표시
    )
    fig_yearly_job_ratio.update_traces(textposition='inside')
    fig_yearly_job_ratio.update_xaxes(type='category')
    st.plotly_chart(fig_yearly_job_ratio, use_container_width=True)
    
    st.markdown("---")

else:
    st.warning("분석 조건에 맞는 퇴직 예정자 데이터가 없습니다. (2026년 이후 퇴직 & 67년생 이상)")