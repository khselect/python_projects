import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import weibull_min


from matplotlib import font_manager


f_path = '/Library/Fonts/Arial Unicode.ttf'
font_manager.FontProperties(fname = f_path).get_name()

from matplotlib import rc

rc('font', family='Arial Unicode MS')

# Weibull 분포 파라미터
shape = 3.0  # 형상모수 (β)
scale = 20000  # 척도모수 (η)

# 시간 범위 설정
t = np.linspace(0, 60000, 1000)

# 생존함수(Survival Function)와 누적분포함수(CDF)
cdf = weibull_min.cdf(t, c=shape, scale=scale)  # 누적고장확률
sf = 1 - cdf  # 생존확률

# 고장률 함수 (Hazard Function)
pdf = weibull_min.pdf(t, c=shape, scale=scale)
hazard = pdf / sf

# 그래프 그리기
fig, axs = plt.subplots(2, 1, figsize=(10, 8))

# 1. 생존함수
axs[0].plot(t, sf, label='생존확률(Survival Function)', color='green')
axs[0].set_title('펌프의 생존확률 (형상모수=2.0, 척도모수=20,000시간)')
axs[0].set_xlabel('시간 (시간)')
axs[0].set_ylabel('생존확률')
axs[0].grid(True)
axs[0].legend()

# 2. 고장률 함수
axs[1].plot(t, hazard, label='고장률(Hazard Function)', color='red')
axs[1].set_title('펌프의 고장률 변화')
axs[1].set_xlabel('시간 (시간)')
axs[1].set_ylabel('고장률')
axs[1].grid(True)
axs[1].legend()

plt.tight_layout()
plt.show()
