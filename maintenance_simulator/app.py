import os
from flask import Flask, render_template, request, jsonify
import math

# --- Flask 앱 설정 ---
app = Flask(__name__)

# --- 웹 페이지 라우트 ---
@app.route('/')
def simulator():
    """시뮬레이터 메인 페이지를 렌더링합니다."""
    return render_template('simulator.html')

# --- 시뮬레이션 API 라우트 ---
@app.route('/api/simulate', methods=['POST'])
def run_simulation():
    """입력값을 받아 TBM과 PdM 시나리오를 시뮬레이션하고 결과를 반환합니다."""
    params = request.get_json()

    # --- 입력 변수 (입력값 또는 기본값) ---
    simulation_period = params.get('simulation_period', 60) # 시뮬레이션 기간 (개월)
    num_components = params.get('num_components', 100)     # 대상 부품 수량

    # 비용 모델
    c_part = params.get('c_part', 500000)               # 부품 원가 (원)
    c_planned_labor = params.get('c_planned_labor', 100000) # 계획 정비 인건비 (원)
    c_unplanned_labor = params.get('c_unplanned_labor', 300000) # 긴급 정비 인건비 (원)
    c_downtime = params.get('c_downtime', 1000000)       # 기회손실 비용 (원/시간)
    mttr = params.get('mttr', 4)                         # 평균 수리 시간 (시간)

    # 부품 수명 특성
    eta = params.get('eta', 18)                          # 척도모수 η (개월) - MTBF와 유사
    b10_life = params.get('b10_life', 16)                # B10 수명 (개월)
    
    # TBM 전략
    tbm_interval = params.get('tbm_interval', 4)         # 주기정비 교체 주기 (개월)
    tbm_failure_prob = params.get('tbm_failure_prob', 0.01) # 주기 내 고장 확률 (%)

    # --- 시나리오 A: 주기정비 (TBM) 비용 계산 ---
    tbm_results = {}
    if tbm_interval > 0:
        # 1. 총 교체 횟수 (부품 1개당)
        replacements_per_comp_tbm = math.floor(simulation_period / tbm_interval)
        total_replacements_tbm = replacements_per_comp_tbm * num_components

        # 2. 총 계획 교체 비용
        tbm_results['planned_cost'] = total_replacements_tbm * (c_part + c_planned_labor)

        # 3. 총 잔존 수명 폐기 비용
        wasted_life_per_replacement = eta - tbm_interval
        if wasted_life_per_replacement > 0 and eta > 0:
            wasted_value_per_replacement = c_part * (wasted_life_per_replacement / eta)
            tbm_results['wasted_life_cost'] = total_replacements_tbm * wasted_value_per_replacement
        else:
            tbm_results['wasted_life_cost'] = 0

        # 4. 총 주기 내 고장 비용
        cost_per_failure = c_part + c_unplanned_labor + (c_downtime * mttr)
        num_failures_tbm = total_replacements_tbm * tbm_failure_prob
        tbm_results['failure_cost'] = num_failures_tbm * cost_per_failure
        
        # 5. TBM 총비용
        tbm_results['total_cost'] = tbm_results['planned_cost'] + tbm_results['wasted_life_cost'] + tbm_results['failure_cost']
        tbm_results['total_replacements'] = total_replacements_tbm
    else:
        tbm_results = {'total_cost': 0, 'planned_cost': 0, 'wasted_life_cost': 0, 'failure_cost': 0, 'total_replacements': 0}


    # --- 시나리오 B: 예측정비 (PdM) 비용 계산 ---
    pdm_results = {}
    if b10_life > 0:
        # 1. 총 교체 횟수 (부품 1개당)
        replacements_per_comp_pdm = simulation_period / b10_life
        total_replacements_pdm = replacements_per_comp_pdm * num_components

        # 2. 총 계획 교체 비용 (90%는 B10 주기에 맞춰 계획 교체)
        num_planned_pdm = total_replacements_pdm * 0.9
        pdm_results['planned_cost'] = num_planned_pdm * (c_part + c_planned_labor)

        # 3. 총 조기 고장 비용 (10%는 B10 도달 전 고장)
        num_failures_pdm = total_replacements_pdm * 0.1
        pdm_results['failure_cost'] = num_failures_pdm * cost_per_failure
        
        # 4. PdM에서는 잔존 수명 폐기 비용이 발생하지 않음
        pdm_results['wasted_life_cost'] = 0
        
        # 5. PdM 총비용
        pdm_results['total_cost'] = pdm_results['planned_cost'] + pdm_results['failure_cost']
        pdm_results['total_replacements'] = total_replacements_pdm
    else:
        pdm_results = {'total_cost': 0, 'planned_cost': 0, 'wasted_life_cost': 0, 'failure_cost': 0, 'total_replacements': 0}

    return jsonify({'tbm': tbm_results, 'pdm': pdm_results})

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, port=5002)