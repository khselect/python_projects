# 인천 1호선 초미세먼지 · 통행량 통합 분석 대시보드 (셀프호스팅)

Streamlit(프론트) + FastAPI(백엔드) + PostgreSQL + Docker Compose + Cloudflare Tunnel 로 구성된
셀프호스팅용 애플리케이션입니다. `/Users/.../Projects/인천1호선_초미세먼지_통행량_통합대시보드.html`
(단일 HTML 프로토타입)과 동일한 분석 로직을 백엔드 API + Streamlit UI 구조로 재구현했습니다.

## 구성

```
incheon_air_traffic_dashboard/
├── backend/            FastAPI + SQLAlchemy (PostgreSQL)
│   ├── app/
│   │   ├── main.py         API 진입점
│   │   ├── models.py       ORM 모델 (stations / pm25_hourly / traffic_hourly)
│   │   ├── analysis.py     예측(계절성분해/선형회귀) · 상관계수 로직
│   │   ├── crud.py         DB 조회 헬퍼
│   │   └── routers/        /api/stations, /api/trend, /api/cross, /api/map
│   └── etl/load_data.py    엑셀 원본 → PostgreSQL 적재 스크립트
├── frontend/            Streamlit (3개 탭: 추세예측 / 교차분석 / 지도)
├── data/                원본 엑셀 배치 폴더 (data/README.md 참고)
├── cloudflared/ingress_snippet.yml   기존 Cloudflare Tunnel에 추가할 설정 예시
├── docker-compose.yml
└── .env.example
```

## 1. 로컬/맥미니에서 기동

```bash
cp .env.example .env
# .env 열어서 POSTGRES_PASSWORD 등 값을 실제 값으로 변경

# data/ 폴더에 원본 엑셀 2개 배치 (data/README.md 참고)

docker compose up -d --build
```

## 2. 데이터 적재 (최초 1회, 원본 갱신 시 재실행)

```bash
docker compose exec backend python -m etl.load_data \
  --pm25 /data/<초미세먼지파일>.xlsx \
  --traffic /data/<통행량파일>.xlsx
```

적재 로그에 `역 33개, PM2.5 레코드 20832건, 통행량 레코드 1320건` 형태로 출력되면 정상입니다.
(통행량 원본의 마지막 두 행 `1호선 계`는 노선 전체 합계이므로 자동으로 제외되며, 병합 셀 파싱 버그로
`송도달빛축제공원` 하차값이 전체 합계로 덮어써지던 문제도 이 ETL에서 수정되었습니다.)

## 3. 로컬 확인

http://localhost:8501 (.env의 FRONTEND_PORT) 로 접속해 3개 탭이 정상 동작하는지 확인합니다.
백엔드 API는 http://localhost:8010/docs (.env의 BACKEND_PORT) 에서 Swagger 문서로 바로 확인 가능합니다.

## 4. Cloudflare Tunnel 연결 (air.sielain.com)

맥미니에 이미 parts.sielain.com용 cloudflared 터널이 떠 있다는 전제 하에, **새 터널을 만들지 않고
기존 터널의 config.yml에 ingress 규칙만 추가**합니다. `cloudflared/ingress_snippet.yml` 파일에
추가할 규칙 예시와 적용 절차(DNS 라우트 등록, 서비스 재시작)가 정리되어 있습니다.

핵심 요약:
```bash
cloudflared tunnel route dns <터널이름 또는 ID> air.sielain.com
# config.yml의 ingress 목록에 air.sielain.com → http://localhost:8501 규칙 추가 후
# cloudflared 서비스 재시작
```

## 5. 운영 참고사항

- **좌표 정확도**: 역사 좌표는 인천교통공사 공식 역정보(도로명주소) 및 공개 지리정보 기반 근사치입니다.
  공공데이터포털의 정밀 GPS CSV(`data.go.kr`)는 브라우저 클릭 다운로드 방식이라 이 프로젝트의
  자동화 파이프라인으로는 받아올 수 없었습니다. 실측 좌표가 있다면 `backend/etl/load_data.py`의
  `LINE1_COORDS` 딕셔너리 값을 교체하세요.
- **기간 불일치**: PM2.5(2024-10)와 통행량(2026-04)은 수집 시기가 달라 절대 시점 비교가 아닌
  "하루 중 시간대별 평균 패턴" 교차비교입니다(탭2 참고).
- **DB 백업**: `docker compose exec postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql`
- **재적재**: 새 원본 파일로 교체 후 `etl.load_data`를 다시 실행하면 기존 데이터를 지우고 새로 적재합니다
  (`load()` 함수 내부에서 delete 후 insert).

## 6. 로컬 검증 이력

이 코드는 Docker가 없는 개발 환경에서 다음까지 검증되었습니다:
- ETL 스크립트: 실제 원본 엑셀 2개로 SQLite 대상 적재 성공(PM2.5 20,832건, 통행량 1,320건, 버그 수정 검증 포함)
- FastAPI: `TestClient`로 `/api/stations`, `/api/trend/forecast`(seasonal/linear), `/api/cross/*`, `/api/map`
  전체 엔드포인트 응답 확인, HTML 프로토타입에서 계산한 상관계수 값과 일치 확인
- Streamlit: uvicorn 백엔드에 연결한 상태로 `streamlit run` 기동 후 HTTP 200 및 에러 없는 로그 확인
- **Docker Compose/Cloudflare Tunnel 자체는 이 환경에 Docker 데몬이 없어 실제 빌드·터널 연결까지는
  검증하지 못했습니다.** 맥미니에서 `docker compose up -d --build` 실행 시 이슈가 있으면 알려주세요.
