import os
import random
import numpy as np
import math
from collections import Counter
from datetime import datetime, date, timedelta

from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy

from analysis import perform_weibull_analysis

# 시나리오 프리셋 (필요 시 수치 조정)
SCENARIOS = {
    "A": {  # 기본 TBM vs 보수적 PdM
        "tbm_interval_months": 12,   # TBM 교체 주기(월)
        "tbm_failure_prob": 0.05,    # TBM 주기 내 기대 고장비율
        "pdm_beta": 1.8,             # PdM Weibull 형상
        "pdm_eta_months": 18         # PdM Weibull 척도(월)
    },
    "B": {  # 절감 목표(예: ~20%) 가정 강화
        "tbm_interval_months": 12,
        "tbm_failure_prob": 0.05,
        "pdm_beta": 2.0,
        "pdm_eta_months": 20
    }
}

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

# 2025.08.08
# 히스토리가 거의 없을 때는 표준편차를 평균의 25%로 보수 가정(“lazy formula”) 하여도 충분히 직관적인 범위가 나옴
# 이후 데이터가 쌓이면 자연히 더 좁은 구간으로 줄어듬
# 3. 고장 예측 기반 예산 계획 (향후 90일 예측으로 수정)
@app.route('/api/cost/budget_forecast')
def budget_forecast():
    """
    총 예상 교체비용(향후 horizon_days) + 95% CI + 부품별/장비별 상세 + 근거데이터.
    - parts: 기존처럼 part_id별 {count, unit_cost_mean, unit_cost_std, total_cost}
    - devices: device_id별 {expected_count, expected_cost, top_parts}
    - explain: 표로 바로 보여줄 수 있는 행 데이터(산식/근거 탭)
    - 항상 200 OK로 반환(프런트가 깨지지 않도록)
    쿼리: ?budget=600000000(기본 6억) & ?horizon_days=90
    """
    # -------------------- 파라미터 --------------------
    try:
        budget = int(float(request.args.get('budget', 600_000_000)))
    except Exception:
        budget = 600_000_000
    try:
        horizon_days = int(float(request.args.get('horizon_days', 90)))
    except Exception:
        horizon_days = 90
    H = max(1, horizon_days) * 24  # 시간

    # -------------------- 헬퍼 --------------------
    def _as_dt(x):
        if x is None: return None
        if isinstance(x, datetime): return x
        if isinstance(x, date):     return datetime(x.year, x.month, x.day)
        return None

    def _get_eta_beta(info: dict):
        if not isinstance(info, dict): return None, None
        eta = info.get('eta') or info.get('eta_hours') or info.get('scale')
        beta = info.get('beta') or info.get('shape')
        b10  = info.get('b10_life') or info.get('b10') or info.get('B10')
        if eta is None and b10 is not None:
            try:
                beta0 = float(beta) if beta is not None else 1.8
                eta = float(b10) / ((-math.log(0.9)) ** (1.0 / beta0))
                beta = beta0
            except Exception:
                eta = None
        try:  eta = float(eta) if eta is not None else None
        except: eta = None
        try:  beta = float(beta) if beta is not None else None
        except: beta = None
        return eta, beta

    def _F_weibull(t, eta, beta):
        if eta is None or beta is None or eta <= 0 or beta <= 0 or t <= 0:
            return 0.0
        x = (t / eta) ** beta
        x = min(max(x, 0.0), 700.0)
        return 1.0 - math.exp(-x)

    def _get_device_id(comp):
        # 스키마에 따라 가능한 필드들을 순차 탐색
        for k in ('device_id', 'equipment_id', 'asset_id', 'system_id', 'line_id'):
            if hasattr(comp, k):
                v = getattr(comp, k)
                if v not in (None, ''):
                    return str(v)
        return 'UNKNOWN'

    def _get_serial(comp):
        for k in ('serial_number', 'serial', 'sn'):
            if hasattr(comp, k):
                v = getattr(comp, k)
                if v not in (None, ''):
                    return str(v)
        return ''

    # -------------------- 데이터 로드 --------------------
    try:
        analysis_results = perform_weibull_analysis() if 'perform_weibull_analysis' in globals() else None
    except Exception:
        analysis_results = None

    try:
        active_components = PumpData.query.filter_by(removal_date=None).all() if 'PumpData' in globals() else []
        if not active_components and 'PumpData' in globals():
            active_components = PumpData.query.all()
    except Exception:
        active_components = []

    if not isinstance(analysis_results, dict) or not active_components:
        return jsonify({
            "total_forecast_cost": 0,
            "total_sigma": 0,
            "ci95_low": 0, "ci95_high": 0,
            "budget": budget, "budget_variance": int(budget),
            "forecast_details": {},
            "device_breakdown": [],
            "explain": []
        })

    # -------------------- 1) 각 설비의 '다음 H시간 내 고장확률' 계산 --------------------
    now = datetime.utcnow()
    comps = []  # 장비/부품별 확률 및 설명용 원시행
    part_ids_needed = set()

    for comp in active_components:
        part_id = getattr(comp, 'part_id', None)
        if not part_id: 
            continue
        eta, beta = _get_eta_beta(analysis_results.get(part_id) or {})
        if eta is None or beta is None:
            continue

        # 나이 a(시간)
        a = None
        if hasattr(comp, 'operating_hours'):
            try: a = float(comp.operating_hours)
            except: a = None
        if a is None:
            inst = _as_dt(getattr(comp, 'install_date', None))
            if inst is not None:
                a = max(0.0, (now - inst).total_seconds() / 3600.0)
        if a is None:
            continue

        p_next = max(0.0, _F_weibull(a + H, eta, beta) - _F_weibull(a, eta, beta))
        if p_next <= 0:
            continue

        comps.append({
            "device": _get_device_id(comp),
            "part_id": str(part_id),
            "serial": _get_serial(comp),
            "age_h": float(round(a, 2)),
            "eta": float(round(eta, 2)),
            "beta": float(round(beta, 3)),
            "p_next": float(round(p_next, 4))
        })
        part_ids_needed.add(str(part_id))

    if not comps:
        return jsonify({
            "total_forecast_cost": 0,
            "total_sigma": 0,
            "ci95_low": 0, "ci95_high": 0,
            "budget": budget, "budget_variance": int(budget),
            "forecast_details": {},
            "device_breakdown": [],
            "explain": []
        })

    # -------------------- 2) 부품 단가 μ,σ (최근 2년) --------------------
    window_start = date.today() - timedelta(days=730)
    global_costs = []

    if 'PumpData' in globals():
        try:
            hist_all = PumpData.query.filter(
                PumpData.is_failure == True,
                PumpData.removal_date != None,
                PumpData.removal_date >= window_start,
                PumpData.cost != None
            ).all()
            for h in hist_all:
                c = getattr(h, 'cost', None)
                if c is None: continue
                try: c = float(c)
                except: continue
                if c > 0: global_costs.append(c)
        except Exception:
            pass

    global_mu = (sum(global_costs) / len(global_costs)) if len(global_costs) >= 1 else 500_000.0
    if len(global_costs) >= 2:
        gv = sum((c - global_mu) ** 2 for c in global_costs) / (len(global_costs) - 1)
        global_sd = math.sqrt(gv)
    elif len(global_costs) == 1:
        global_sd = global_mu * 0.25
    else:
        global_sd = global_mu * 0.25

    part_stats = {}  # part_id -> (mu, sd)
    if 'PumpData' in globals():
        for pid in part_ids_needed:
            mu = None; sd = None
            try:
                hist = PumpData.query.filter(
                    PumpData.part_id == pid,
                    PumpData.is_failure == True,
                    PumpData.removal_date != None,
                    PumpData.removal_date >= window_start,
                    PumpData.cost != None
                ).all()
                costs = []
                for h in hist:
                    c = getattr(h, 'cost', None)
                    if c is None: continue
                    try: c = float(c)
                    except: continue
                    if c > 0: costs.append(c)
                if len(costs) >= 2:
                    mu = sum(costs) / len(costs)
                    var = sum((c - mu) ** 2 for c in costs) / (len(costs) - 1)
                    sd = math.sqrt(var)
                elif len(costs) == 1:
                    mu = float(costs[0]); sd = mu * 0.25
            except Exception:
                pass
            if mu is None: mu = global_mu
            if sd is None or sd <= 0: sd = max(global_sd, mu * 0.1)
            part_stats[pid] = (float(mu), float(sd))
    else:
        for pid in part_ids_needed:
            part_stats[pid] = (global_mu, max(global_sd, global_mu * 0.1))

    # -------------------- 3) 부품별/장비별/총합 계산 --------------------
    # (a) 부품별 합계
    parts = {}
    for row in comps:
        pid = row['part_id']
        mu, sd = part_stats.get(pid, (global_mu, max(global_sd, global_mu * 0.1)))
        cnt = row['p_next']  # 기대수량(확률)
        cost_est = cnt * mu

        p = parts.setdefault(pid, {"count": 0.0, "unit_cost_mean": int(round(mu)),
                                   "unit_cost_std": int(round(sd)), "total_cost": 0})
        p["count"] += cnt
        p["total_cost"] += int(round(cost_est))

    # (b) 장비별 합계 + 상위 부품 3개
    devices = {}
    for row in comps:
        dev = row['device']; pid = row['part_id']
        mu, sd = part_stats.get(pid, (global_mu, max(global_sd, global_mu * 0.1)))
        cnt = row['p_next']; cost_est = cnt * mu
        d = devices.setdefault(dev, {"expected_count": 0.0, "expected_cost": 0.0, "parts": {}})
        d["expected_count"] += cnt
        d["expected_cost"]  += cost_est
        d["parts"][pid] = d["parts"].get(pid, 0.0) + cost_est

    device_breakdown = []
    for dev, v in devices.items():
        parts_sorted = sorted(v["parts"].items(), key=lambda kv: kv[1], reverse=True)[:3]
        device_breakdown.append({
            "device": dev,
            "expected_count": float(round(v["expected_count"], 2)),
            "expected_cost": int(round(v["expected_cost"])),
            "top_parts": [{"part_id": k, "cost": int(round(val))} for k, val in parts_sorted]
        })
    device_breakdown.sort(key=lambda x: x["expected_cost"], reverse=True)

    # (c) 총합/오차(95% CI)
    sum_mean = sum(p["total_cost"] for p in parts.values())
    sum_var  = 0.0
    for pid, p in parts.items():
        mu, sd = part_stats.get(pid, (global_mu, max(global_sd, global_mu * 0.1)))
        sum_var += float(p["count"]) * (sd ** 2)
    sigma  = math.sqrt(sum_var) if sum_var > 0 else 0.0
    z      = 1.96
    ci_low = max(0, int(round(sum_mean - z * sigma)))
    ci_high= int(round(sum_mean + z * sigma))

    # (d) 근거 표(explain) — 탭에서 그대로 표시 가능
    explain_rows = []
    for row in comps:
        pid = row['part_id']
        mu, sd = part_stats.get(pid, (global_mu, max(global_sd, global_mu * 0.1)))
        explain_rows.append({
            "device": row["device"],
            "part_id": pid,
            "serial": row["serial"],
            "age_hours": row["age_h"],
            "eta": row["eta"], "beta": row["beta"],
            "p_next_90d": row["p_next"],
            "unit_cost_mean": int(round(mu)),
            "expected_cost": int(round(row["p_next"] * mu))
        })

    # -------------------- 응답 --------------------
    return jsonify({
        "total_forecast_cost": int(round(sum_mean)),
        "total_sigma": int(round(sigma)),
        "ci95_low": ci_low, "ci95_high": ci_high,
        "budget": budget, "budget_variance": int(budget - round(sum_mean)),
        "forecast_details": {
            k: {"count": float(round(v["count"], 2)),
                "unit_cost_mean": v["unit_cost_mean"],
                "unit_cost_std": v["unit_cost_std"],
                "total_cost": int(v["total_cost"])}
            for k, v in parts.items()
        },
        "device_breakdown": device_breakdown,
        "explain": explain_rows,
        "assumptions": {
            "method": "expected failures via Weibull CDF difference",
            "horizon_days": horizon_days, "window_days": 730, "ci": 0.95
        }
    })
        
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
    return render_template('simulator.html')

# --- 시뮬레이터 타임라인 라우트 ---
def build_timeseries(params: dict, preset: dict):
    # 1) 입력 파라미터
    months   = int(params.get("simulation_period", 60))
    n_parts  = int(params.get("num_components", 100))
    eta_m    = float(params.get("eta", preset["pdm_eta_months"]))

    c_part   = float(params.get("c_part", 500_000))
    c_plan   = float(params.get("c_planned_labor", 100_000))
    c_unplan = float(params.get("c_unplanned_labor", 300_000))
    c_dt     = float(params.get("c_downtime", 1_000_000))
    mttr     = float(params.get("mttr", 4))

    tbm_interval  = int(params.get("tbm_interval", preset["tbm_interval_months"]))
    tbm_fail_prob = float(params.get("tbm_failure_prob", preset["tbm_failure_prob"]))
    
    b10_life = float(params.get("b10_life", 16))
    beta     = float(params.get("beta", preset["pdm_beta"]))

    # 2) 월별 집계
    timeline = []
    
    # TBM 비용요소
    tbm_replacements_total = 0
    tbm_failures_total = 0
    tbm_planned_cost_total = 0
    tbm_failure_cost_total = 0
    
    # PdM 비용요소
    pdm_replacements_total = 0
    pdm_failures_total = 0
    pdm_planned_cost_total = 0
    pdm_failure_cost_total = 0

    # 와이블 분포 기반 수명 샘플링 (PdM용)
    rng = np.random.default_rng(42)
    lifetimes = rng.weibull(beta, size=n_parts) * eta_m

    for m in range(1, months + 1):
        # --- TBM 계산 ---
        tbm_repl_monthly = n_parts if (m > 0 and m % tbm_interval == 0) else 0
        tbm_fail_monthly = int(round(tbm_repl_monthly * tbm_fail_prob))
        
        planned_cost_monthly = tbm_repl_monthly * (c_part + c_plan)
        failure_cost_monthly = tbm_fail_monthly * (c_part + c_unplan + c_dt * mttr)
        tbm_cost = planned_cost_monthly + failure_cost_monthly
        
        tbm_replacements_total += tbm_repl_monthly
        tbm_failures_total += tbm_fail_monthly
        tbm_planned_cost_total += planned_cost_monthly
        tbm_failure_cost_total += failure_cost_monthly
        
        # --- PdM 계산 ---
        # (m-1, m] 구간에서 수명이 종료된 부품 수
        pdm_repl_monthly = int(np.sum((lifetimes > (m - 1)) & (lifetimes <= m)))
        # B10 정의에 따라 10%는 조기 고장난다고 가정
        pdm_fail_monthly = int(round(pdm_repl_monthly * 0.1)) 
        pdm_repl_planned = pdm_repl_monthly - pdm_fail_monthly

        pdm_planned_cost_monthly = pdm_repl_planned * (c_part + c_plan)
        pdm_failure_cost_monthly_ = pdm_fail_monthly * (c_part + c_unplan + c_dt * mttr)
        pdm_cost = pdm_planned_cost_monthly + pdm_failure_cost_monthly_
        
        pdm_replacements_total += pdm_repl_monthly
        pdm_failures_total += pdm_fail_monthly
        pdm_planned_cost_total += pdm_planned_cost_monthly
        pdm_failure_cost_total += pdm_failure_cost_monthly_

        timeline.append({
            "month": m,
            "tbm_replacements": tbm_repl_monthly, "tbm_failures": tbm_fail_monthly, "tbm_cost": tbm_cost,
            "pdm_replacements": pdm_repl_monthly, "pdm_failures": pdm_fail_monthly, "pdm_cost": pdm_cost
        })

    # --- 최종 결과 집계 ---
    wasted_life = eta_m - tbm_interval
    tbm_wasted_life_cost = (tbm_replacements_total * c_part * (wasted_life / eta_m)) if wasted_life > 0 and eta_m > 0 else 0

    tbm_totals = {
        "total_cost": tbm_planned_cost_total + tbm_failure_cost_total + tbm_wasted_life_cost,
        "planned_cost": tbm_planned_cost_total,
        "wasted_life_cost": tbm_wasted_life_cost,
        "failure_cost": tbm_failure_cost_total,
        "total_replacements": tbm_replacements_total,
    }
    pdm_totals = {
        "total_cost": pdm_planned_cost_total + pdm_failure_cost_total,
        "planned_cost": pdm_planned_cost_total,
        "wasted_life_cost": 0, # PdM은 잔존수명 폐기 비용 0
        "failure_cost": pdm_failure_cost_total,
        "total_replacements": pdm_replacements_total,
    }
    return timeline, tbm_totals, pdm_totals


# --- 시뮬레이션 API 라우트 ---
@app.route('/api/simulate', methods=['POST'])
def run_simulation():
    params = request.get_json()
    scenario_key = (request.args.get("scenario") or params.get("scenario") or "A").upper()
    preset = SCENARIOS.get(scenario_key, SCENARIOS["A"])

    # ⭐️ 수정: build_timeseries 함수를 호출하여 모든 계산을 한 번에 처리
    timeseries, tbm_results, pdm_results = build_timeseries(params, preset)
    
    return jsonify({
        'scenario': scenario_key,
        'tbm': tbm_results,
        'pdm': pdm_results,
        'timeseries': timeseries
    })

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