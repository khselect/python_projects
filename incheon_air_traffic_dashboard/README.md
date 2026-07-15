# 인천 1호선 초미세먼지 · 통행량 통합 분석 대시보드 (셀프호스팅)

**🌐 운영 중: https://air.sielain.com (2026-07-15 개통)**

Streamlit(프론트) + FastAPI(백엔드) + PostgreSQL + Docker Compose + Cloudflare Tunnel 로 구성된
셀프호스팅용 애플리케이션입니다. `/Users/.../Projects/인천1호선_초미세먼지_통행량_통합대시보드.html`
(단일 HTML 프로토타입)과 동일한 분석 로직을 백엔드 API + Streamlit UI 구조로 재구현한 뒤,
웹 업로드 기반 월 단위 누적 적재와 집계 기반 종합 리포트 기능을 확장했습니다.

## 주요 기능 (5개 탭)

| 탭 | 기능 |
|----|------|
| 1. 데이터 업로드·관리 | 통행량/초미세먼지 엑셀 웹 업로드 → 월 단위 누적 적재, 적재 현황 목록 |
| 2. 추세·기간예측 | 역/기간 선택 → PM2.5 계절성분해·선형회귀 예측. PM2.5 기준월 선택 또는 **전체(누적)** 학습 |
| 3. 교차분석 | PM2.5 × 통행량 시간대 패턴 비교 + **사분면 우선순위 산점도** — 전체 평균 기준 4분할, 고농도·고혼잡(우상단 음영) 역을 "주요 관리역"으로 강조·목록화 |
| 4. 지도 | 역사 위치 기반 혼잡도(원 크기) × PM2.5(색상) Plotly 지도, 상위 역 컴팩트 목록 |
| 5. 종합 리포트 | LLM·추론 없이 적재 데이터 집계값을 고정 템플릿에 대입한 사실 요약 + .md 다운로드 |

레이아웃은 스크롤 없이 한 화면에 들어오도록 압축되어 있습니다(상단 고정 헤더 숨김, 폰트·차트 높이 축소).

## 구성

```
incheon_air_traffic_dashboard/
├── backend/            FastAPI + SQLAlchemy (PostgreSQL)
│   ├── app/
│   │   ├── main.py         API 진입점
│   │   ├── models.py       ORM 모델 (stations / pm25_hourly / traffic_hourly)
│   │   ├── analysis.py     예측(계절성분해/선형회귀) · 상관계수 로직
│   │   ├── crud.py         DB 조회 헬퍼
│   │   └── routers/        /api/stations /api/periods /api/trend /api/cross /api/map
│   │                       /api/upload/* /api/datasets /api/report
│   └── etl/load_data.py    엑셀 원본 → PostgreSQL 적재 스크립트 (--append: 월 단위 누적)
├── frontend/            Streamlit 5개 탭: 추세예측 / 교차분석 / 지도 / 데이터 업로드·관리 / 종합 리포트
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

## 2. 데이터 적재

**웹 업로드(권장)**: 대시보드 "4. 데이터 업로드·관리" 탭에서 통행량/초미세먼지 엑셀을 직접 업로드.
- 월 단위 **누적** 적재: 같은 월 재업로드 시 그 월만 교체, 다른 월은 유지
- 통행량 기준월(YYYY-MM)은 직접 입력(파일명에 "2026년 6월" 형태가 있으면 자동 제안),
  초미세먼지는 파일 내 측정시간에서 월 자동 인식
- 업로드 원본은 `data/uploads/`에 보관, 적재 현황은 같은 탭 목록과 `/api/datasets`에서 확인
- 누적된 데이터는 예측(탭1, PM2.5 기준월 선택 또는 전체 누적 학습)·교차분석(탭2)·지도(탭3, 사이드바
  통행량 기준월 선택)·종합 리포트(탭5)에 즉시 반영

**CLI 적재** — 원본 엑셀이 있는 경우:
```bash
docker compose exec backend python -m etl.load_data \
  --pm25 /data/<초미세먼지파일>.xlsx \
  --traffic /data/<통행량파일>.xlsx
```

원본 엑셀이 없는 환경(맥미니)에서는 HTML 프로토타입에서 추출한 JSON으로 적재:
```bash
# data/merged_dataset.json 은 프로토타입 HTML의 data-slot JSON을 추출한 파일
docker compose exec backend python -m etl.load_from_json --json /data/merged_dataset.json
```

적재 로그에 `역 33개, PM2.5 레코드 20832건, 통행량 레코드 1320건` 형태로 출력되면 정상입니다.
(통행량 원본의 마지막 두 행 `1호선 계`는 노선 전체 합계이므로 자동으로 제외되며, 병합 셀 파싱 버그로
`송도달빛축제공원` 하차값이 전체 합계로 덮어써지던 문제도 이 ETL에서 수정되었습니다.)

## 3. 로컬 확인

http://localhost:8501 (.env의 FRONTEND_PORT) 로 접속해 5개 탭이 정상 동작하는지 확인합니다.
백엔드 API는 http://localhost:8010/docs (.env의 BACKEND_PORT) 에서 Swagger 문서로 바로 확인 가능합니다.

## 4. Cloudflare Tunnel 연결 (air.sielain.com)

맥미니의 기존 터널(`sielain_tunnel` 컨테이너, `/Users/sielain/docker` 스택)은 **TUNNEL_TOKEN
기반 원격 관리형**이라 config.yml ingress가 적용되지 않습니다 (parts.sielain.com 배포 때 확인).
라우팅은 두 가지로 구성됩니다:

1. **네트워크 연결(자동)**: 이 프로젝트의 `docker-compose.yml`이 frontend 컨테이너를 기존 터널
   네트워크(`docker_sielain_net`, external)에 함께 연결합니다. `docker compose up` 만으로 완료.

2. **대시보드 라우트 등록(수동, 최초 1회 — 2026-07-15 완료)**: Cloudflare Zero Trust 대시보드에서
   **Networks → Tunnels → sielain-tunnel → Published application routes → Add** 로 등록:
   - Subdomain: `air` / Domain: `sielain.com` / URL: `http://air_traffic_frontend:8501`
   - ⚠ 신규 대시보드 UI는 Service URL에 **프로토콜(`http://`)을 반드시 포함**해야 저장됩니다
     (구 UI의 Type 드롭다운이 URL 프리픽스로 통합됨).
   - 저장 시 DNS CNAME 자동 생성, 터널 재시작 불필요. 상세: `cloudflared/ingress_snippet.yml`

## 5. 운영 참고사항

- **좌표 정확도**: 역사 좌표는 인천교통공사 공식 역정보(도로명주소) 및 공개 지리정보 기반 근사치입니다.
  공공데이터포털의 정밀 GPS CSV(`data.go.kr`)는 브라우저 클릭 다운로드 방식이라 이 프로젝트의
  자동화 파이프라인으로는 받아올 수 없었습니다. 실측 좌표가 있다면 `backend/etl/load_data.py`의
  `LINE1_COORDS` 딕셔너리 값을 교체하세요.
- **기간 불일치**: PM2.5(2024-10)와 통행량(2026-04)은 수집 시기가 달라 절대 시점 비교가 아닌
  "하루 중 시간대별 평균 패턴" 교차비교입니다(탭2 참고).
- **DB 백업**: `docker compose exec postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql`
- **재적재**: `etl.load_data` 기본 실행은 전체 삭제 후 재적재, `--append --period YYYY-MM`은 해당 월
  통행량만 교체(다른 월·PM2.5·역 정보 유지). 웹 업로드는 항상 월 단위 교체(누적) 방식입니다.
- **⚠ 업로드 공개 노출**: 탭4 업로드는 air.sielain.com 방문자 누구나 사용할 수 있습니다.
  parts 대시보드의 크롤러 데이터 삭제 사고 전례가 있으므로, 필요 시 parts처럼 Cloudflare Access
  (이메일 OTP)로 보호하는 것을 권장합니다.

## 6. 로컬 검증 이력

이 코드는 Docker가 없는 개발 환경에서 다음까지 검증되었습니다:
- ETL 스크립트: 실제 원본 엑셀 2개로 SQLite 대상 적재 성공(PM2.5 20,832건, 통행량 1,320건, 버그 수정 검증 포함)
- FastAPI: `TestClient`로 `/api/stations`, `/api/trend/forecast`(seasonal/linear), `/api/cross/*`, `/api/map`
  전체 엔드포인트 응답 확인, HTML 프로토타입에서 계산한 상관계수 값과 일치 확인
- Streamlit: uvicorn 백엔드에 연결한 상태로 `streamlit run` 기동 후 HTTP 200 및 에러 없는 로그 확인
- ~~Docker Compose/Cloudflare Tunnel 자체는 이 환경에 Docker 데몬이 없어 실제 빌드·터널 연결까지는
  검증하지 못했습니다.~~ → **2026-07-14 맥미니에서 배포 완료**: `docker compose up -d --build` 3개 컨테이너
  기동, 역 33개·PM2.5 20,832건·통행량 1,320건 적재, 전체 API + Streamlit 응답
  확인, 터널 네트워크(`docker_sielain_net`)에서 `air_traffic_frontend:8501` 도달 확인.
- **2026-07-15 air.sielain.com 개통 확인** (HTTPS 200): Cloudflare 대시보드 Published application route
  등록 완료. 같은 날 기능 확장 검증:
  - 실제 원본 엑셀로 재적재 — 통행량 2026-04(전체 적재) + 2026-05(`--append` 누적), PM2.5 2024-10
  - 업로드 API — 통행량 재업로드(월 교체, 1,320건 유지), PM2.5 업로드(20,832건), 기준월 형식 오류 400 거절,
    원본 `data/uploads/` 보관 확인
  - `/api/datasets` 월별 현황, `/api/report` 집계 리포트, `/api/trend/forecast?month=` 월 필터 응답 확인
  - 교훈: FastAPI `Form`/`UploadFile` 사용 시 `python-multipart` 의존성 필요 (requirements.txt에 추가됨)
- **2026-07-15~16 UI 개선**:
  - 지도를 folium(Leaflet) → Plotly(OpenStreetMap)로 교체 — folium은 비활성 탭 안에서 0×0으로
    초기화되어 지도가 표시되지 않는 문제(`streamlit-folium` + `st.tabs`)가 있었음
  - 탭 순서 변경(데이터 업로드·관리를 첫 탭으로), 한 화면 압축 레이아웃(고정 헤더 숨김 — 숨기지 않으면
    줄인 상단 여백에서 제목이 헤더 바에 가려 잘림), 통행량 단위 표기 정정(일→월)
  - 교차분석 우측을 **사분면 우선순위 산점도**로 개편: 기준선 = 공통 역 전체 평균, 우상단
    (고농도·고혼잡) 음영 + 빨간 마커·라벨, 주요 관리역 텍스트 목록 자동 생성. 프로토타입 HTML에도 동일 반영
  - 교훈: Streamlit 마크다운에서 한 문단에 `~`가 2개면 취소선으로 해석되어 사라짐 — 범위 표기는 `–` 사용
