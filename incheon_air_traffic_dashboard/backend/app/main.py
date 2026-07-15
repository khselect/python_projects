from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import stations, trend, cross, map_, upload, report

app = FastAPI(
    title="인천 1호선 초미세먼지·통행량 통합 분석 API",
    description="PM2.5 추세/예측, 미세먼지-통행량 교차분석, 혼잡도-미세먼지 지도 데이터를 제공합니다.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Streamlit 프론트엔드(내부망/터널)에서만 호출되므로 전체 허용. 필요시 도메인 제한.
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stations.router)
app.include_router(stations.periods_router)
app.include_router(trend.router)
app.include_router(cross.router)
app.include_router(map_.router)
app.include_router(upload.router)
app.include_router(report.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
