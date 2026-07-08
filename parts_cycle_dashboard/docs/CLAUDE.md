# CLAUDE.md

이 문서는 Claude(및 다른 AI 코딩 어시스턴트)가 `parts_cycle_dashboard` 저장소에서
작업할 때 참고하는 가이드입니다. 상세한 API/알고리즘 명세는
[`docs/기술상세서.md`](./기술상세서.md)를 참고하세요.

## 프로젝트 개요

설비 부품(펌프 등)의 교체 이력을 관리하고, Weibull 신뢰성 분석으로 수명을 예측하며,
TBM(시간기준 정비) 대비 PdM(예지정비) 비용을 시뮬레이션하는 Flask 웹 애플리케이션입니다.

- **백엔드**: Flask + Flask-SQLAlchemy + SQLite (`pump_data.db`)
- **프론트엔드**: 서버 사이드 렌더링(Jinja2) + Bootstrap 5 + Chart.js (SPA 프레임워크 없음)
- **분석 엔진**: `analysis.py` — SciPy 기반 중도절단 Weibull MLE

## 실행 방법

```bash
# 최초 1회: 의존성 설치 + DB 초기화(가상 데이터 150개 생성)
pip install -r requirements.txt
flask init-db

# 개발 서버 실행 (기본 포트 5001)
python app.py
```

프로덕션은 `gunicorn app:app` (Procfile/Dockerfile 참고, 포트 8000).

## 디렉터리 구조

```
app.py                  # 라우트 + API 전체 (단일 파일, ~750줄)
analysis.py              # Weibull MLE 분석 모듈
templates/               # Jinja2 템플릿 (페이지별 1파일)
  _navigation.html        # 공용 상단 탭 네비게이션 (include)
  dashboard.html           # 종합 대시보드 (수직 서브탭 + KPI + 차트)
  cost_analysis.html, simulator.html, analysis_view.html, infographic.html, index.html
static/js/
  dashboard.js             # /dashboard, /analysis-view 페이지 전용 차트/KPI 로직
  cost_analysis.js          # /cost-analysis, /simulator 페이지 전용 로직
static/lectures/          # 교육/인수인계용 인터랙티브 HTML 자료
docs/                     # 기술 문서 (이 파일, 기술상세서.md)
ver_1.0/                  # 이전 버전 스냅샷 — 참고용, 수정하지 않음
```

`app.py`는 라우트가 단일 파일에 모두 있습니다. 새 API를 추가할 때도 기존 관례를 따라
같은 파일에 `@app.route(...)` 함수로 추가하세요 (blueprint로 분리되어 있지 않음).

## 코드 컨벤션 / 이 저장소에서 지켜온 패턴

- **주석/변수명은 한국어 혼용이 기본값**입니다. 기존 코드 스타일(한국어 주석, 한국어 UI
  라벨)을 따르세요 — 영어로 통일하려 하지 마세요.
- **프론트엔드는 순수 Bootstrap 5 + Chart.js + vanilla JS**입니다. React/Vue 등 신규
  프레임워크를 도입하지 마세요.
- **차트 색상은 `static/js/dashboard.js` 상단의 `PALETTE`/`INK`/`STATUS` 상수를
  재사용**하세요. 임의의 hex 코드를 새로 만들지 말 것 — 컬러블라인드 세이프 검증을 거친
  고정 팔레트입니다. 새 차트를 추가할 때도 `CATEGORICAL_ORDER`를 그대로 슬라이스해서
  씁니다.
- **차트/시각화를 새로 추가하거나 색상을 바꿀 때는 `dataviz` 스킬을 먼저 확인**하세요
  (폼 선택 → 색상 배정 → 검증 순서, part-to-whole은 파이 대신 막대를 우선 고려 등).
- 새 API를 추가하면 `docs/기술상세서.md`의 API 명세 표도 함께 갱신하세요.
- `ver_1.0/`은 이전 버전의 스냅샷입니다. 현재 앱과 무관하므로 수정하지 마세요.

## 아키텍처 메모

- **인증 없음** — 내부/사내 도구로 설계되어 로그인 절차가 없습니다. 배포 시 접근 제어가
  필요하다면 리버스 프록시/VPN 레벨에서 처리해야 합니다.
- **DB는 SQLite 단일 파일**(`pump_data.db`)입니다. 동시 쓰기 부하가 큰 환경에는
  적합하지 않으므로, 운영 규모가 커지면 Postgres 등으로 전환을 검토하세요.
- **`/dashboard` 서브탭**은 Bootstrap의 `nav-pills` + `tab-content`를 사용하며, 탭이
  화면에 표시된 뒤(`shown.bs.tab`) 해당 차트를 지연 로드합니다. 새 서브탭을 추가할 때는
  `initializeDashboardTabs()`의 `chartLoadFunctions` 매핑에 등록해야 동작합니다.
- **`analysis.py`의 Weibull 분석은 요청마다 재계산**됩니다(캐싱 없음). 데이터가 많아지면
  `/api/analysis_results` 응답이 느려질 수 있습니다.

## 작업 시 주의할 점

- Flask 개발 서버는 `debug=True`로 실행되어 템플릿/코드 변경 시 자동 리로드됩니다. 다만
  **정적 파일(JS/CSS)은 브라우저 캐시로 인해 변경이 즉시 반영되지 않을 수 있으니**,
  변경 확인 시 강력 새로고침(Cmd/Ctrl+Shift+R)을 안내하세요.
- `pump_data.db`는 저장소에 커밋된 실제 데이터 파일입니다. `flask init-db`는
  **기존 데이터를 모두 삭제(`db.drop_all()`)하고 가상 데이터로 재생성**하므로,
  사용자에게 확인 없이 실행하지 마세요.
- 부품 ID는 코드에 하드코딩되어 있습니다(`DCU`, `EPR2A`, `TIDK`, `TICC`, `엔코더` —
  `app.py`의 `_generate_fake_data`). 실제 운영 데이터는 `/add` 폼을 통해 별도로
  입력됩니다.
