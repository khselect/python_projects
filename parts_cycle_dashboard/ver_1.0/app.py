import os
import random
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
    install_date = db.Column(db.Date, nullable=False)
    removal_date = db.Column(db.Date, nullable=True)
    is_failure = db.Column(db.Boolean, nullable=False)

    def __repr__(self):
        return f'<PumpData {self.part_id}>'

# --- 웹 페이지 라우트 ---
@app.route('/')
def index():
    all_data = PumpData.query.order_by(PumpData.install_date.desc()).all()
    return render_template('index.html', all_data=all_data)

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/add', methods=['POST'])
def add_data():
    part_id = request.form.get('part_id')
    install_date_str = request.form.get('install_date')
    removal_date_str = request.form.get('removal_date')
    is_failure = request.form.get('is_failure') == 'on'

    install_date = datetime.strptime(install_date_str, '%Y-%m-%d').date()
    removal_date = None
    if removal_date_str:
        removal_date = datetime.strptime(removal_date_str, '%Y-%m-%d').date()

    new_data = PumpData(
        part_id=part_id,
        install_date=install_date,
        removal_date=removal_date,
        is_failure=is_failure
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
@app.route('/api/analysis_results')
def analysis_results():
    results = perform_weibull_analysis()
    return jsonify(results)

@app.route('/api/part_distribution')
def part_distribution():
    parts = [data.part_id for data in PumpData.query.all()]
    part_counts = Counter(parts)
    labels = list(part_counts.keys())
    data = list(part_counts.values())
    return jsonify({'labels': labels, 'data': data})

@app.route('/api/failure_ranking')
def failure_ranking():
    failed_parts = [data.part_id for data in PumpData.query.filter_by(is_failure=True).all()]
    failure_counts = Counter(failed_parts)
    ranked_parts = failure_counts.most_common()
    labels = [item[0] for item in ranked_parts]
    data = [item[1] for item in ranked_parts]
    return jsonify({'labels': labels, 'data': data})

# @app.route('/api/lifespan_distribution')
# def lifespan_distribution():
#     lifespans = []
#     for data in PumpData.query.filter_by(is_failure=True).all():
#         if data.removal_date and data.install_date:
#             lifespan = (data.removal_date - data.install_date).days
#             lifespans.append(lifespan)
#     return jsonify({'data': lifespans})

# 1. 고장 히트맵 API (기존 /api/lifespan_distribution 대체)
@app.route('/api/failure_heatmap')
def failure_heatmap():
    failures = PumpData.query.filter_by(is_failure=True).all()
    
    # { '부품ID': {'년-월': 고장 횟수} } 형태의 데이터 생성
    heatmap_data = {}
    for f in failures:
        if f.removal_date:
            month_year = f.removal_date.strftime('%Y-%m')
            part_id = f.part_id
            heatmap_data.setdefault(part_id, {}).setdefault(month_year, 0)
            heatmap_data[part_id][month_year] += 1
    
    # Chart.js 히트맵 플러그인 형식에 맞게 데이터 가공: [{x, y, v}]
    dataset = []
    for part_id, monthly_data in heatmap_data.items():
        for month, count in monthly_data.items():
            dataset.append({'x': month, 'y': part_id, 'v': count})
            
    # 히트맵의 x, y축 레이블 생성
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

# @app.route('/api/time_to_failure')
# def time_to_failure():
#     failure_times = []
#     all_parts = sorted(list(set(data.part_id for data in PumpData.query.all())))
#     for part_id in all_parts:
#         lifespans = []
#         for data in PumpData.query.filter_by(part_id=part_id, is_failure=True).all():
#             if data.removal_date and data.install_date:
#                 lifespans.append((data.removal_date - data.install_date).days)
#         if lifespans:
#             failure_times.append({'part_id': part_id, 'lifespans': lifespans})
#     return jsonify(failure_times)

# 2. 고장 수명 비율 API (기존 /api/time_to_failure 대체)
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
        
    results.sort(key=lambda x: x['ratio']) # 오름차순으로 정렬
    labels = [r['part_id'] for r in results]
    data = [r['ratio'] for r in results]
    return jsonify({'labels': labels, 'data': data})

@app.route('/api/failure_rate_trend')
def failure_rate_trend():
    failures = PumpData.query.filter_by(is_failure=True).all()
    monthly_failures = Counter(f.removal_date.strftime('%Y-%m') for f in failures if f.removal_date)
    sorted_months = sorted(monthly_failures.keys())
    labels = sorted_months
    data = [monthly_failures[month] for month in sorted_months]
    return jsonify({'labels': labels, 'data': data})


# --- 가상 데이터 생성을 위한 헬퍼 함수 ---
def _generate_fake_data(num_records=150):
    """실제 가상 데이터를 생성하는 내부 함수"""
    part_ids = ['EPR2A', 'TIDK', 'TICC', 'DCU', '엔코더']
    start_date_obj = date(2022, 1, 1)
    end_date_obj = date.today()
    for _ in range(num_records):
        part_id = random.choice(part_ids)
        total_days = (end_date_obj - start_date_obj).days
        install_date = start_date_obj + timedelta(days=random.randint(0, total_days))
        removal_date = None
        is_failure = False
        if random.random() < 0.4:
            is_failure = True
            lifespan = random.randint(10, 365 * 2)
            removal_date = install_date + timedelta(days=lifespan)
            if removal_date > end_date_obj:
                removal_date = end_date_obj
        elif random.random() < 0.15:
            is_failure = False
            lifespan = random.randint(30, 365 * 3)
            removal_date = install_date + timedelta(days=lifespan)
            if removal_date > end_date_obj:
                removal_date = end_date_obj
        if is_failure and removal_date is None:
            lifespan = random.randint(10, 365)
            removal_date = install_date + timedelta(days=lifespan)
            if removal_date > end_date_obj:
               removal_date = end_date_obj
        new_data = PumpData(
            part_id=part_id, install_date=install_date,
            removal_date=removal_date, is_failure=is_failure
        )
        db.session.add(new_data)
    db.session.commit()

# --- 사용자 정의 CLI 명령어 ---
@app.cli.command("init-db")
def init_db_command():
    """데이터베이스를 초기화하고 가상 데이터를 생성합니다."""
    db.drop_all()  # 기존 테이블 삭제
    db.create_all() # 새 테이블 생성
    print("데이터베이스를 초기화했습니다.")
    _generate_fake_data()
    print("초기 가상 데이터 150개를 생성했습니다.")

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    app.run(debug=True, port=5001)