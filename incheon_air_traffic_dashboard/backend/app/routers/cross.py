"""과제2: 초미세먼지 x 통행량 교차분석 API

⚠ 두 데이터의 수집 시기가 다름(PM2.5: 2024-10 / 통행량: 2026-04)을 감안하여
시각 단위(시간대) 패턴만을 비교하는 API. 절대 시점 비교가 아님.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas, analysis
from ..database import get_db

router = APIRouter(prefix="/api/cross", tags=["cross"])


def _overlap_stations(db: Session):
    return [s for s in crud.get_all_stations(db) if s.has_pm25]


@router.get("/{station}", response_model=schemas.CrossOut)
def cross_station(station: str, db: Session = Depends(get_db)):
    st = crud.get_station_by_name(db, station)
    if st is None or not st.has_pm25:
        raise HTTPException(404, f"'{station}' 역은 PM2.5-통행량 공통 데이터가 없습니다.")

    pm_hour_avg = crud.get_pm25_hour_avg(db, st.id)
    traffic = crud.get_traffic(db, st.id)
    board = traffic.get("승차", {}).get("hourly", [])
    alight = traffic.get("하차", {}).get("hourly", [])
    hour_labels = traffic.get("승차", {}).get("hour_labels") or traffic.get("하차", {}).get("hour_labels")
    if not hour_labels or not board or not alight:
        raise HTTPException(404, "통행량 데이터가 없습니다.")

    total = [b + a for b, a in zip(board, alight)]
    pm_aligned = analysis.align_pm_to_traffic_buckets(pm_hour_avg, hour_labels)
    corr = analysis.pearson(pm_aligned, total)

    return schemas.CrossOut(
        station=station, hour_labels=hour_labels, pm_aligned=pm_aligned,
        traffic_total=total, correlation=corr,
    )


@router.get("/", response_model=schemas.ScatterOut)
def cross_scatter(db: Session = Depends(get_db)):
    stations = _overlap_stations(db)
    points = []
    for s in stations:
        pm_hour_avg = crud.get_pm25_hour_avg(db, s.id)
        avg_pm = sum(pm_hour_avg.values()) / len(pm_hour_avg) if pm_hour_avg else 0.0
        total = crud.get_traffic_total(db, s.id)
        points.append(schemas.ScatterPointOut(station=s.name, avg_pm25=avg_pm, total_traffic=total))

    corr = analysis.pearson([p.avg_pm25 for p in points], [float(p.total_traffic) for p in points])
    return schemas.ScatterOut(points=points, correlation=corr)
