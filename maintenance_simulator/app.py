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

    # --- 입력 변수 ---
    simulation_period = params.get('simulation_period', 60)
    num_components = params.get('num_components', 100)
    c_part = params.get('c_part', 500000)
    c_planned_labor = params.get('c_planned_labor', 100000)
    c_unplanned_labor = params.get('c_unplanned_labor', 300000)
    c_downtime = params.get('c_downtime', 1000000)
    mttr = params.get('mttr', 4)
    eta = params.get('eta', 18)
    b10_life = params.get('b10_life', 16)
    tbm_interval = params.get('tbm_interval', 12)
    tbm_failure_prob = params.get('tbm_failure_prob', 0.05)

    cost_per_failure = c_part + c_unplanned_labor + (c_downtime * mttr)

    # --- 시나리오 A: 주기정비 (TBM) 비용 계산 ---
    tbm_results = {}
    if tbm_interval > 0:
        replacements_per_comp = math.floor(simulation_period / tbm_interval)
        total_replacements = replacements_per_comp * num_components
        
        tbm_results['planned_cost'] = total_replacements * (c_part + c_planned_labor)
        
        wasted_life = eta - tbm_interval
        tbm_results['wasted_life_cost'] = (total_replacements * c_part * (wasted_life / eta)) if wasted_life > 0 and eta > 0 else 0
        
        num_failures = total_replacements * tbm_failure_prob
        tbm_results['failure_cost'] = num_failures * cost_per_failure
        
        tbm_results['total_cost'] = tbm_results['planned_cost'] + tbm_results['wasted_life_cost'] + tbm_results['failure_cost']
        tbm_results['total_replacements'] = total_replacements
    else:
        tbm_results = {'total_cost': 0, 'planned_cost': 0, 'wasted_life_cost': 0, 'failure_cost': 0, 'total_replacements': 0}

    # --- 시나리오 B: 예측정비 (PdM) 비용 계산 ---
    pdm_results = {}
    if b10_life > 0:
        replacements_per_comp = simulation_period / b10_life
        total_replacements = replacements_per_comp * num_components
        
        pdm_results['planned_cost'] = (total_replacements * 0.9) * (c_part + c_planned_labor)
        pdm_results['failure_cost'] = (total_replacements * 0.1) * cost_per_failure
        pdm_results['wasted_life_cost'] = 0
        pdm_results['total_cost'] = pdm_results['planned_cost'] + pdm_results['failure_cost']
        pdm_results['total_replacements'] = total_replacements
    else:
        pdm_results = {'total_cost': 0, 'planned_cost': 0, 'wasted_life_cost': 0, 'failure_cost': 0, 'total_replacements': 0}

    return jsonify({'tbm': tbm_results, 'pdm': pdm_results})

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, port=5002)