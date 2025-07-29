import os
import random
import math
from collections import Counter
from datetime import datetime, date, timedelta

from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy

from analysis import perform_weibull_analysis

# --- 기본 설정 ---
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'pump_data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 데이터베이스 모델 정의 ---
class PumpData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(100), nullable=True)
    install_date = db.Column(db.Date, nullable=False)
    removal_date = db.Column(db.Date, nullable=True)
    is_failure = db.Column(db.Boolean, nullable=False)
    cost = db.Column(db.Integer, nullable=True)
    priority = db.Column(db.String(50), nullable=True, default='중간')

    def __repr__(self):
        return f'<PumpData {self.part_id}>'

# --- 웹 페이지 라우트 ---
@app.route('/')
def index():
    all_data = PumpData.query.order_by(PumpData.install_date.desc()).all()
    return render_template('index.html', all_data=all_data)

@app.route('/infographic')
def infographic():
    """인포그래픽 페이지를 렌더링합니다."""
    return render_template('infographic.html')

@app.route('/analysis-view')
def analysis_view():
    """수명 분석 결과 페이지를 렌더링합니다."""
    return render_template('analysis_view.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/cost-analysis')
def cost_analysis():
    """비용 분석 대시보드 페이지를 렌더링합니다."""
    return render_template('cost_analysis.html')

@app.route('/add', methods=['POST'])
def add_data():
    part_id = request.form.get('part_id')
    serial_number = request.form.get('serial_number')
    install_date_str = request.form.get('install_date')
    removal_date_str = request.form.get('removal_date')
    is_failure = request.form.get('is_failure') == 'on'
    cost = request.form.get('cost', type=int, default=0)
    priority = request.form.get('priority')

    install_date = datetime.strptime(install_date_str, '%Y-%m-%d').date()
    removal_date = None
    if removal_date_str:
        removal_date = datetime.strptime(removal_date_str, '%Y-%m-%d').date()

    new_data = PumpData(
        part_id=part_id,
        serial_number=serial_number,
        install_date=install_date,
        removal_date=removal_date,
        is_failure=is_failure,
        cost=cost,
        priority=priority
    )
    db.session.add(new_data)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete_data(id):
    data_to_delete = PumpData.query.get_or_404(id)
    db.session.delete(data_to_delete)
    db.session.commit()
    return redirect(url_for('index'))


# --- API 라우트 ---
# @app.route('/api/pm_watchlist')
# def pm_watchlist():
#     try:
#         analysis_results = perform_weibull_analysis()
#         active_components = PumpData.query.filter_by(removal_date=None).all()
#         watchlist = []
#         for comp in active_components:
#             part_id = comp.part_id
#             if part_id in analysis_results and analysis_results[part_id].get('b10_life'):
#                 b10_life = analysis_results[part_id]['b10_life']
#                 if b10_life and b10_life > 0:
#                     operating_hours = (datetime.utcnow().date() - comp.install_date).total_seconds() / 3600
#                     usage_ratio = (operating_hours / b10_life) * 100
#                     status = '정상'
#                     if usage_ratio >= 200: status = '위험'
#                     elif usage_ratio >= 100: status = '주의'
                    
#                     if status != '정상':
#                         watchlist.append({
#                             'db_id': comp.id,
#                             'part_id': part_id,
#                             'serial_number': comp.serial_number,
#                             'install_date': comp.install_date.strftime('%Y-%m-%d'),
#                             'operating_hours': round(operating_hours),
#                             'b10_life': round(b10_life),
#                             'usage_ratio': round(usage_ratio),
#                             'status': status
#                         })
#         watchlist.sort(key=lambda x: x['usage_ratio'], reverse=True)
#         return jsonify(watchlist)
#     except Exception as e:
#         print(f"Error in /api/pm_watchlist: {e}")
#         return jsonify({'error': str(e)}), 500

@app.route('/api/part_distribution')
def part_distribution():
    parts = [data.part_id for data in PumpData.query.all()]
    part_counts = Counter(parts)
    return jsonify({'labels': list(part_counts.keys()), 'data': list(part_counts.values())})

@app.route('/api/failure_ranking')
def failure_ranking():
    failed_parts = [data.part_id for data in PumpData.query.filter_by(is_failure=True).all()]
    failure_counts = Counter(failed_parts)
    ranked_parts = failure_counts.most_common()
    labels = [item[0] for item in ranked_parts]
    data = [item[1] for item in ranked_parts]
    return jsonify({'labels': labels, 'data': data})

@app.route('/api/failure_lifespan_ratio')
def failure_lifespan_ratio():
    results = []
    part_ids = [p.part_id for p in db.session.query(PumpData.part_id).distinct()]
    for part_id in part_ids:
        total_op_days = 0
        failure_op_days = 0
        all_components = PumpData.query.filter_by(part_id=part_id).all()
        for comp in all_components:
            end_date = comp.removal_date if comp.removal_date else date.today()
            if comp.install_date:
                op_days = (end_date - comp.install_date).days
                total_op_days += op_days
                if comp.is_failure:
                    failure_op_days += op_days
        ratio = (failure_op_days / total_op_days * 100) if total_op_days > 0 else 0
        results.append({'part_id': part_id, 'ratio': ratio})
    results.sort(key=lambda x: x['ratio'])
    labels = [r['part_id'] for r in results]
    data = [r['ratio'] for r in results]
    return jsonify({'labels': labels, 'data': data})

@app.route('/api/analysis_results')
def analysis_results():
    results = perform_weibull_analysis()
    return jsonify(results)

@app.route('/api/failure_heatmap')
def failure_heatmap():
    failures = PumpData.query.filter_by(is_failure=True).all()
    heatmap_data = {}
    for f in failures:
        if f.removal_date:
            month_year = f.removal_date.strftime('%Y-%m')
            part_id = f.part_id
            heatmap_data.setdefault(part_id, {}).setdefault(month_year, 0)
            heatmap_data[part_id][month_year] += 1
    dataset = []
    for part_id, monthly_data in heatmap_data.items():
        for month, count in monthly_data.items():
            dataset.append({'x': month, 'y': part_id, 'v': count})
    x_labels = sorted(list(set(d['x'] for d in dataset)))
    y_labels = sorted(list(set(d['y'] for d in dataset)))
    return jsonify({'dataset': dataset, 'x_labels': x_labels, 'y_labels': y_labels})

@app.route('/api/installation_trend')
def installation_trend():
    install_dates = [data.install_date for data in PumpData.query.all()]
    date_counts = Counter(d.strftime('%Y-%m') for d in install_dates)
    sorted_months = sorted(date_counts.keys())
    labels = sorted_months
    data = [date_counts[month] for month in sorted_months]
    return jsonify({'labels': labels, 'data': data})

@app.route('/api/failure_rate_trend')
def failure_rate_trend():
    failures = PumpData.query.filter_by(is_failure=True).all()
    monthly_failures = Counter(f.removal_date.strftime('%Y-%m') for f in failures if f.removal_date)
    sorted_months = sorted(monthly_failures.keys())
    labels = sorted_months
    data = [monthly_failures[month] for month in sorted_months]
    return jsonify({'labels': labels, 'data': data})

# ⭐️ 비용 분석을 위한 신규 API 3개 ⭐️

# 1. 부품별 총 교체 비용 (지난 1년)
@app.route('/api/cost/replacement_last_year')
def replacement_cost_last_year():
    one_year_ago = date.today() - timedelta(days=365)
    
    # 지난 1년간 '고장'으로 '제거'된 부품 조회
    replacements = PumpData.query.filter(
        PumpData.is_failure == True,
        PumpData.removal_date >= one_year_ago
    ).all()
    
    cost_by_part = {}
    for item in replacements:
        cost_by_part.setdefault(item.part_id, 0)
        if item.cost:
            cost_by_part[item.part_id] += item.cost
            
    sorted_costs = sorted(cost_by_part.items(), key=lambda x: x[1], reverse=True)
    
    labels = [item[0] for item in sorted_costs]
    data = [item[1] for item in sorted_costs]
    
    return jsonify({'labels': labels, 'data': data})

# 2. 시간당 운영 비용 (가성비 분석)
@app.route('/api/cost/cost_per_hour')
def cost_per_hour():
    results = []
    part_ids = [p.part_id for p in db.session.query(PumpData.part_id).distinct()]

    for part_id in part_ids:
        total_cost = 0
        total_hours = 0
        
        # '고장'으로 수명이 다한 부품만 계산에 포함
        failed_components = PumpData.query.filter_by(part_id=part_id, is_failure=True).all()
        
        if not failed_components:
            continue

        for comp in failed_components:
            if comp.cost and comp.removal_date and comp.install_date:
                lifespan_hours = (comp.removal_date - comp.install_date).total_seconds() / 3600
                if lifespan_hours > 0:
                    total_cost += comp.cost
                    total_hours += lifespan_hours
        
        avg_cost_per_hour = total_cost / total_hours if total_hours > 0 else 0
        if avg_cost_per_hour > 0:
            results.append({'part_id': part_id, 'cost_per_hour': avg_cost_per_hour})
            
    # 시간당 비용이 낮은 순(가성비 좋은 순)으로 정렬
    results.sort(key=lambda x: x['cost_per_hour'])
    
    labels = [r['part_id'] for r in results]
    data = [r['cost_per_hour'] for r in results]
    
    return jsonify({'labels': labels, 'data': data})

# 3. 고장 예측 기반 예산 계획 (향후 90일 예측으로 수정)
@app.route('/api/cost/budget_forecast')
def budget_forecast():
    try:
        analysis_results = perform_weibull_analysis()
        active_components = PumpData.query.filter_by(removal_date=None).all()
        
        next_quarter_hours = 90 * 24 # 90일을 시간으로 변환
        forecast = {} 

        for comp in active_components:
            part_id = comp.part_id
            if part_id in analysis_results and analysis_results[part_id].get('b10_life'):
                b10_life = analysis_results[part_id]['b10_life']
                
                if b10_life and b10_life > 0:
                    operating_hours = (datetime.utcnow().date() - comp.install_date).total_seconds() / 3600
                    
                    # ⭐️ 수정: 현재 수명이 B10 미만이지만, 90일 후에는 B10을 초과할 부품을 예측
                    if operating_hours < b10_life and (operating_hours + next_quarter_hours) >= b10_life:
                        forecast.setdefault(part_id, {'count': 0, 'total_cost': 0})
                        forecast[part_id]['count'] += 1
                        if comp.cost:
                            forecast[part_id]['total_cost'] += comp.cost
                            
        total_forecast_cost = sum(v['total_cost'] for v in forecast.values())
        
        return jsonify({'forecast_details': forecast, 'total_forecast_cost': total_forecast_cost})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ⭐️ 신규 기능: 교체 우선순위 부품 추천 API ⭐️
# @app.route('/api/recommendations/replacement_priority')
# def replacement_priority():
#     # 1. 부품별 고장 횟수 계산
#     failed_parts = [data.part_id for data in PumpData.query.filter_by(is_failure=True).all()]
#     failure_counts = Counter(failed_parts)
    
#     # 2. 부품별 최고 중요도 확인
#     part_priorities = {}
#     priority_map = {'높음': 3, '중간': 2, '낮음': 1}
    
#     all_parts = db.session.query(PumpData.part_id, PumpData.priority).distinct().all()
#     for part_id, priority in all_parts:
#         # 가장 높은 중요도를 해당 부품의 대표 중요도로 설정
#         current_priority_score = priority_map.get(priority, 0)
#         if part_id not in part_priorities or current_priority_score > part_priorities[part_id]['score']:
#             part_priorities[part_id] = {'text': priority, 'score': current_priority_score}

#     # 3. 고장 빈도와 중요도를 조합하여 우선순위 점수 계산
#     recommendations = []
#     for part_id, failure_count in failure_counts.items():
#         priority_info = part_priorities.get(part_id, {'text': 'N/A', 'score': 0})
#         # 점수 = 고장횟수 * 중요도 가중치
#         priority_score = failure_count * priority_info['score']
        
#         recommendations.append({
#             'part_id': part_id,
#             'failure_count': failure_count,
#             'priority': priority_info['text'],
#             'score': priority_score
#         })
        
#     # 최종 점수가 높은 순으로 정렬
#     recommendations.sort(key=lambda x: x['score'], reverse=True)
    
#     return jsonify(recommendations)

# ⭐️ 통합된 예방 정비 우선순위 API ⭐️
@app.route('/api/priority_maintenance')
def priority_maintenance():
    try:
        # 1. 와이블 분석으로 B10 수명 예측
        analysis_results = perform_weibull_analysis()
        
        # 2. 부품별 중요도 점수화
        priority_map = {'높음': 3, '중간': 2, '낮음': 1}
        
        recommendations = []
        active_components = PumpData.query.filter_by(removal_date=None).all()

        for comp in active_components:
            part_id = comp.part_id
            
            # 3. B10 수명 기반 위험도 계산
            usage_ratio = 0
            if part_id in analysis_results and analysis_results[part_id].get('b10_life'):
                b10_life = analysis_results[part_id]['b10_life']
                if b10_life and b10_life > 0:
                    operating_hours = (datetime.utcnow().date() - comp.install_date).total_seconds() / 3600
                    usage_ratio = (operating_hours / b10_life) * 100

            # 4. 종합 위험 점수 계산 (사용률이 70% 이상인 부품만 대상)
            if usage_ratio >= 70:
                priority_score = priority_map.get(comp.priority, 1)
                cost = comp.cost if comp.cost else 0
                
                # 위험 점수 = (B10 수명 사용률) * (중요도 점수) * (비용 가중치)
                risk_score = (usage_ratio / 100) * priority_score * (1 + cost / 100000)
                
                recommendations.append({
                    'part_id': part_id,
                    'serial_number': comp.serial_number,
                    'priority': comp.priority,
                    'cost': cost,
                    'usage_ratio': round(usage_ratio),
                    'risk_score': round(risk_score, 2)
                })

        # 최종 위험 점수가 높은 순으로 정렬
        recommendations.sort(key=lambda x: x['risk_score'], reverse=True)
        
        return jsonify(recommendations)
    except Exception as e:
        print(f"Error in /api/priority_maintenance: {e}")
        return jsonify({'error': str(e)}), 500

# --- 시뮬레이터 페이지 라우트 ---
@app.route('/simulator')
def simulator_page():
    """유지보수 전략 비용 시뮬레이터 페이지를 렌더링합니다."""
    # base.html을 상속받으므로, base.html에 필요한 변수가 있다면 전달해야 합니다.
    # 예를 들어, 모든 부품 목록이 필요하다면 여기서 조회해서 전달할 수 있습니다.
    return render_template('simulator.html')

# --- 시뮬레이션 API 라우트 ---
@app.route('/api/simulate', methods=['POST'])
def run_simulation():
    """
    입력값을 받아 TBM과 PdM 시나리오를 시뮬레이션하고 결과를 JSON으로 반환합니다.
    이 함수는 maintenance_simulator 프로젝트의 로직과 동일합니다.
    """
    params = request.get_json()

    # --- 입력 변수 (입력값 또는 기본값) ---
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

    # --- 공통 계산: 고장 1회당 총 손실 비용 ---
    cost_per_failure = c_part + c_unplanned_labor + (c_downtime * mttr)

    # --- 시나리오 A: 주기정비 (TBM) 비용 계산 ---
    tbm_results = {}
    if tbm_interval > 0:
        # 총 교체 횟수
        replacements_per_comp = math.floor(simulation_period / tbm_interval)
        total_replacements = replacements_per_comp * num_components
        
        # 계획 교체 비용
        tbm_results['planned_cost'] = total_replacements * (c_part + c_planned_labor)
        
        # 잔존 수명 폐기 비용
        wasted_life = eta - tbm_interval
        tbm_results['wasted_life_cost'] = (total_replacements * c_part * (wasted_life / eta)) if wasted_life > 0 and eta > 0 else 0
        
        # 주기 내 고장 비용
        num_failures = total_replacements * tbm_failure_prob
        tbm_results['failure_cost'] = num_failures * cost_per_failure
        
        # TBM 총 비용
        tbm_results['total_cost'] = tbm_results['planned_cost'] + tbm_results['wasted_life_cost'] + tbm_results['failure_cost']
        tbm_results['total_replacements'] = total_replacements
    else:
        tbm_results = {'total_cost': 0, 'planned_cost': 0, 'wasted_life_cost': 0, 'failure_cost': 0, 'total_replacements': 0}

    # --- 시나리오 B: 예측정비 (PdM) 비용 계산 ---
    pdm_results = {}
    if b10_life > 0:
        # 총 교체 횟수 (B10 주기에 따름)
        replacements_per_comp = simulation_period / b10_life
        total_replacements = replacements_per_comp * num_components
        
        # 계획 교체 비용 (90%는 계획대로 교체)
        pdm_results['planned_cost'] = (total_replacements * 0.9) * (c_part + c_planned_labor)
        
        # 조기 고장 비용 (10%는 B10 이전에 고장)
        pdm_results['failure_cost'] = (total_replacements * 0.1) * cost_per_failure
        
        # PdM에서는 잔존 수명 폐기 비용이 발생하지 않음
        pdm_results['wasted_life_cost'] = 0
        
        # PdM 총 비용
        pdm_results['total_cost'] = pdm_results['planned_cost'] + pdm_results['failure_cost']
        pdm_results['total_replacements'] = total_replacements
    else:
        pdm_results = {'total_cost': 0, 'planned_cost': 0, 'wasted_life_cost': 0, 'failure_cost': 0, 'total_replacements': 0}

    return jsonify({'tbm': tbm_results, 'pdm': pdm_results})

# --- 가상 데이터 생성을 위한 헬퍼 함수 ---
def _generate_fake_data(num_records=150):
    """실제 가상 데이터를 생성하는 내부 함수"""
    priorities = ['높음', '중간', '낮음']
    part_ids = ['DCU', 'EPR2A', 'TIDK', 'TICC', '엔코더']
    start_date_obj = date(2023, 1, 1)
    end_date_obj = date.today()
    
    for i in range(num_records):
        part_id = random.choice(part_ids)
        serial_number = f"SN-{random.randint(1000,9999)}-{i+1}"
        cost = random.randint(5, 300) * 1000
        priority = random.choice(priorities)
        
        total_days = (end_date_obj - start_date_obj).days
        install_date = start_date_obj + timedelta(days=random.randint(0, total_days))
        
        removal_date = None
        is_failure = False

        if random.random() < 0.4:
            is_failure = True
            lifespan = random.randint(10, 365 * 2)
            removal_date = install_date + timedelta(days=lifespan)
            if removal_date > end_date_obj: removal_date = end_date_obj
        elif random.random() < 0.15:
            is_failure = False
            lifespan = random.randint(30, 365 * 3)
            removal_date = install_date + timedelta(days=lifespan)
            if removal_date > end_date_obj: removal_date = end_date_obj
            
        if is_failure and removal_date is None:
           lifespan = random.randint(10, 365)
           removal_date = install_date + timedelta(days=lifespan)
           if removal_date > end_date_obj: removal_date = end_date_obj

        # ⭐️ 문제 해결: 생성된 모든 변수를 PumpData 객체에 전달 ⭐️
        new_data = PumpData(
            part_id=part_id,
            serial_number=serial_number,
            install_date=install_date,
            removal_date=removal_date,
            is_failure=is_failure,
            cost=cost,
            priority=priority
        )
        db.session.add(new_data)
    db.session.commit()

# --- 사용자 정의 CLI 명령어 ---
@app.cli.command("init-db")
def init_db_command():
    """데이터베이스를 초기화하고 가상 데이터를 생성합니다."""
    db.drop_all()
    db.create_all()
    print("✅ 데이터베이스를 초기화했습니다.")
    _generate_fake_data()
    print(f"✅ 초기 가상 데이터 150개를 생성했습니다.")

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, port=5001)
