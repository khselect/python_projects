from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from analysis import perform_weibull_analysis

# --- 기본 설정 ---
# 현재 파일의 절대 경로
base_dir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# SQLite 데이터베이스 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'pump_data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# --- 데이터베이스 모델 정의 ---
class PumpData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.String(100), nullable=False)
    install_date = db.Column(db.Date, nullable=False)
    removal_date = db.Column(db.Date, nullable=True) # 고장나지 않은 경우 비어있을 수 있음
    is_failure = db.Column(db.Boolean, nullable=False)

    def __repr__(self):
        return f'<PumpData {self.part_id}>'

# --- 라우트(경로) 정의 ---
@app.route('/')
def index():
    """ 메인 페이지: 데이터 목록 표시 및 입력 폼 """
    all_data = PumpData.query.order_by(PumpData.install_date.desc()).all()
    return render_template('index.html', all_data=all_data)

@app.route('/add', methods=['POST'])
def add_data():
    """ 새로운 데이터 추가 """
    part_id = request.form.get('part_id')
    install_date_str = request.form.get('install_date')
    removal_date_str = request.form.get('removal_date')
    # 'is_failure' 체크박스는 체크되면 'on' 값을 가지며, 체크되지 않으면 전송되지 않습니다.
    is_failure = request.form.get('is_failure') == 'on'
    
    # 문자열을 날짜 객체로 변환
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
    """ 데이터 삭제 """
    data_to_delete = PumpData.query.get_or_404(id)
    db.session.delete(data_to_delete)
    db.session.commit()
    return redirect(url_for('index'))
    

@app.route('/api/analysis_results')
def analysis_results():
    """ 분석 결과를 JSON 형태로 반환하는 API """
    results = perform_weibull_analysis()
    return jsonify(results)

# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    # 애플리케이션 컨텍스트 내에서 데이터베이스 생성
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)