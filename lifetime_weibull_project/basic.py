import pandas as pd
import numpy as np
from scipy.stats import weibull_min
import matplotlib.pyplot as plt
from datetime import datetime
from matplotlib import font_manager
import platform

# OS에 따라 폰트 설정
if platform.system() == 'Windows':
    font_name = 'Malgun Gothic'
elif platform.system() == 'Darwin':  # macOS
    font_name = 'AppleGothic'
else:  # Linux
    font_name = 'NanumGothic'  # 사전에 설치되어 있어야 함

plt.rcParams['font.family'] = font_name
plt.rcParams['axes.unicode_minus'] = False  # 마이너스 부호 깨짐 방지

f_path = '/Library/Fonts/Arial Unicode.ttf'
font_manager.FontProperties(fname = f_path).get_name()
# 데이터 파싱 및 정리
data = {
    '부품 ID': ['P001', 'P002', 'P003', 'P004', 'P005'],
    '사용 시간 (시간)': [18500, 21000, 17000, 19500, 22000],
    '고장 여부 (Y/N)': ['Y', 'Y', 'N', 'Y', 'Y'],
    '설치 일자': ['2021-01-01', '2021-02-15', '2021-03-10', '2021-04-20', '2021-05-30'],
    '제거 일자': ['2023-02-10', '2023-03-25', '', '2023-05-01', '2023-06-15'],
    '환경 조건 / 부하 조건': ['표준', '고온', '표준', '고진동', '표준']
}

df = pd.DataFrame(data)

# 날짜 문자열을 datetime으로 변환
def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d") if date_str else None

df['설치 일자'] = df['설치 일자'].apply(parse_date)
df['제거 일자'] = df['제거 일자'].apply(parse_date)

# 검열 데이터용 현재 날짜
current_date = datetime.strptime('2025-05-29', '%Y-%m-%d')

# 수명(시간)과 이벤트 여부 설정
df['수명 (시간)'] = df['사용 시간 (시간)']
df['event_observed'] = df['고장 여부 (Y/N)'] == 'Y'

# 고장 데이터만 추출 (검열 제외)
failed_data = df[df['event_observed']]['수명 (시간)'].values

# 와이블 분포 적합 (위치 파라미터 0으로 고정)
shape, loc, scale = weibull_min.fit(failed_data, floc=0)
beta = shape
eta = scale

print(f"추정된 형상 모수 (β): {beta:.2f}")
print(f"추정된 척도 모수 (η): {eta:.2f} 시간")
print("참고: P003(검열 데이터)은 scipy 적합에서 제외됨")

# 플롯 1: 와이블 생존 함수
plt.figure(figsize=(10, 6))
t = np.linspace(0, max(df['수명 (시간)']) * 1.2, 1000)
survival_prob = weibull_min.sf(t, shape, loc=0, scale=scale)
plt.plot(t, survival_prob, label='와이블 생존 함수', color='black')
plt.title('펌프 부품의 와이블 생존 함수')
plt.xlabel('시간 (시간)')
plt.ylabel('생존 확률')
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig('weibull_survival_function.png')

# 플롯 2: 부품별 생존 곡선
plt.figure(figsize=(10, 6))
colors = {'표준': 'blue', '고온': 'red', '고진동': 'green'}

for idx, row in df.iterrows():
    t_val = row['수명 (시간)']
    condition = row['환경 조건 / 부하 조건']
    if row['event_observed']:
        plt.plot([0, t_val], [1.0, 0.0],
                 label=f"{row['부품 ID']} ({condition})",
                 color=colors[condition], linestyle='--')
    else:
        surv = weibull_min.sf([t_val], shape, loc=0, scale=scale)[0]
        plt.plot([0, t_val, max(df['수명 (시간)'])],
                 [1.0, surv, surv],
                 label=f"{row['부품 ID']} ({condition}, 검열)",
                 color=colors[condition], linestyle=':')

plt.title('펌프 부품별 개별 생존 곡선')
plt.xlabel('시간 (시간)')
plt.ylabel('생존 확률')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig('individual_survival_curves.png')
plt.close()

plt.tight_layout()
plt.show()