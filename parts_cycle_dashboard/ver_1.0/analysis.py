import pandas as pd
import numpy as np
from scipy.stats import weibull_min
from scipy.optimize import minimize
from sqlalchemy import create_engine
from datetime import datetime

# --- 와이블 분석을 위한 새로운 핵심 함수 ---
def weibull_log_likelihood_censored(params, t, e):
    """
    중도 절단(censored) 데이터를 포함한 와이블 분포의 로그 우도 함수.
    이 함수는 최적화(minimize)의 대상이 됩니다.
    
    Args:
        params (list): [beta (형상모수), eta (척도모수)]
        t (array): 수명 시간 데이터
        e (array): 고장 여부 이벤트 데이터 (1=고장, 0=중도절단)
        
    Returns:
        float: 음의 로그 우도 값 (최소화해야 하므로)
    """
    beta, eta = params[0], params[1]
    
    # 파라미터가 유효한 범위를 벗어나면 매우 큰 값을 반환하여 제외
    if beta <= 0 or eta <= 0:
        return np.inf
        
    # 고장난 데이터(event=1)에 대한 우도 계산
    log_likelihood_failure = np.sum(np.log(weibull_min.pdf(t[e==1], c=beta, scale=eta)))
    
    # 중도 절단된 데이터(event=0)에 대한 우도 계산 (생존 함수)
    log_likelihood_censored = np.sum(np.log(weibull_min.sf(t[e==0], c=beta, scale=eta)))
    
    # 전체 로그 우도의 합 (최소화를 위해 음수로 변환)
    return -(log_likelihood_failure + log_likelihood_censored)


def perform_weibull_analysis(db_uri='sqlite:///pump_data.db'):
    """
    데이터베이스에서 펌프 데이터를 읽어와 부품 ID별로 와이블 분석을 수행합니다.
    """
    engine = create_engine(db_uri)
    try:
        df = pd.read_sql_table('pump_data', engine)
    except ValueError:
        return {}

    if df.empty:
        return {}

    df['removal_date'] = pd.to_datetime(df['removal_date'])
    df['install_date'] = pd.to_datetime(df['install_date'])
    
    df['lifetime_hours'] = (df['removal_date'].fillna(datetime.utcnow()) - df['install_date']).dt.total_seconds() / 3600
    df['event'] = df['is_failure'].astype(int)
    
    # 수명 시간이 0 이하인 데이터는 분석에서 제외
    df = df[df['lifetime_hours'] > 0].copy()

    results = {}
    
    for part_id, group in df.groupby('part_id'):
        lifetimes = group['lifetime_hours'].values
        events = group['event'].values
        
        if sum(events) < 2:
            results[part_id] = {
                'error': '고장 데이터가 부족하여 신뢰성 있는 분석이 어렵습니다.',
                'beta': None, 'eta': None, 'b10_life': None, 'plot_data': None
            }
            continue

        try:
            # --- 분석 로직 변경 ---
            # 초기 추정값 설정 (평균 수명 시간 기준)
            initial_params = [1.5, np.mean(lifetimes)]
            
            # 최적화 함수를 사용하여 로그 우도를 최소화하는 파라미터(beta, eta)를 찾음
            solution = minimize(
                fun=weibull_log_likelihood_censored,
                x0=initial_params,
                args=(lifetimes, events),
                method='Nelder-Mead'
            )

            # 최적화 결과에서 파라미터 추출
            beta, eta = solution.x

        except Exception as e:
            results[part_id] = {
                'error': f'분석 계산 중 오류 발생: {e}',
                'beta': None, 'eta': None, 'b10_life': None, 'plot_data': None
            }
            continue

        max_life = lifetimes.max()
        x_vals = pd.Series(range(0, int(max_life * 1.5), 50))
        survival_prob = weibull_min.sf(x_vals, c=beta, scale=eta)

        results[part_id] = {
            'error': None,
            'beta': round(beta, 2),
            'eta': round(eta, 0),
            'b10_life': round(weibull_min.ppf(0.1, c=beta, scale=eta), 0),
            'plot_data': {'x': x_vals.tolist(), 'y': survival_prob.tolist()}
        }
        
    return results