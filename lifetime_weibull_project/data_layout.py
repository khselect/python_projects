import pandas as pd
import numpy as np
from scipy.stats import weibull_min
import matplotlib.pyplot as plt
from datetime import datetime
from matplotlib import font_manager
import platform

# 한글 폰트 설정
if platform.system() == 'Windows':
    plt.rcParams['font.family'] = 'Malgun Gothic'
elif platform.system() == 'Darwin':
    plt.rcParams['font.family'] = 'AppleGothic'
else:
    plt.rcParams['font.family'] = 'NanumGothic'  # 설치 필요

plt.rcParams['axes.unicode_minus'] = False

# 데이터셋
data = {
    '부품 ID': ['차상장치', '제동장치', '보조전원장치', '출입문장치', '서비스장치'],
    '사용 시간 (시간)': [18500, 21000, 17000, 19500, 22000],
    '고장 여부 (Y/N)': ['Y', 'Y', 'N', 'Y', 'Y'],
    '설치 일자': ['2021-01-01', '2021-02-15', '2021-03-10', '2021-04-20', '2021-05-30'],
    '제거 일자': ['2023-02-10', '2023-03-25', '', '2023-05-01', '2023-06-15'],
    '환경 조건 / 부하 조건': ['표준', '고온', '표준', '고진동', '표준']
}
df = pd.DataFrame(data)

# 날짜 파싱
def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d") if date_str else None

df['설치 일자'] = df['설치 일자'].apply(parse_date)
df['제거 일자'] = df['제거 일자'].apply(parse_date)

# 수명/이벤트 플래그 설정
df['수명 (시간)'] = df['사용 시간 (시간)']
df['event_observed'] = df['고장 여부 (Y/N)'] == 'Y'

# 와이블 분포 개별 적합
weibull_params = {}
x_vals = np.linspace(0, max(df['수명 (시간)']) * 1.2, 1000)

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle("부품별 와이블 분포 곡선 및 수명주기 비교", fontsize=16)

for i, row in df.iterrows():
    part_id = row['부품 ID']
    t = row['수명 (시간)']
    observed = row['event_observed']

    if observed:
        # 단일 데이터 기반 분포는 신뢰도 낮지만 예시로 적합 시도
        shape, loc, scale = weibull_min.fit([t], floc=0)
        weibull_params[part_id] = (shape, scale)

        sf = weibull_min.sf(x_vals, shape, loc=0, scale=scale)

        ax = axes[i // 3][i % 3]
        ax.plot(x_vals, sf, label=f'{part_id}\nβ={shape:.2f}, η={scale:.0f}')
        ax.set_title(f'{part_id} 와이블 곡선')
        ax.set_xlabel('시간 (시간)')
        ax.set_ylabel('생존 확률')
        ax.grid(True)
        ax.legend()
    else:
        ax = axes[i // 3][i % 3]
        ax.text(0.3, 0.5, f'{part_id}:\n검열 데이터\n적합 제외',
                fontsize=12, ha='center', va='center')
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f'{part_id} (검열)')

# 막대그래프 (6번째 subplot)
ax_bar = axes[1][2]
df_sorted = df.sort_values('수명 (시간)')
ax_bar.bar(df_sorted['부품 ID'], df_sorted['수명 (시간)'], color='skyblue')
ax_bar.set_title('부품별 수명주기 (시간)')
ax_bar.set_ylabel('수명 (시간)')
ax_bar.grid(True, axis='y')

plt.tight_layout(rect=[0, 0, 1, 0.95])
plt.savefig("component_lifetime_weibull_summary.png")
plt.show()

# 모수 출력
print("\n📊 부품별 와이블 분포 모수:")
for part_id, (beta, eta) in weibull_params.items():
    print(f" - {part_id}: 형상(β) = {beta:.2f}, 척도(η) = {eta:.0f}")
