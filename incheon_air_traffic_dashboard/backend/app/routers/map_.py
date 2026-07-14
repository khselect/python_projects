"""과제3: 역사 위치 기반 혼잡도-미세먼지 상관관계 지도 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas, analysis
from ..database import get_db

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("", response_model=schemas.MapOut)
def map_data(db: Session = Depends(get_db)):
    stations = crud.get_all_stations(db)
    points = []
    for s in stations:
        avg_pm = None
        if s.has_pm25:
            hour_avg = crud.get_pm25_hour_avg(db, s.id)
            avg_pm = sum(hour_avg.values()) / len(hour_avg) if hour_avg else None
        congestion = crud.get_traffic_total(db, s.id)
        points.append(schemas.MapPointOut(
            station=s.name, lat=s.lat, lon=s.lon, avg_pm25=avg_pm, congestion=congestion,
        ))

    with_both = [p for p in points if p.avg_pm25 is not None and p.congestion is not None]
    corr = analysis.pearson([p.avg_pm25 for p in with_both], [float(p.congestion) for p in with_both])

    top_cong = sorted(with_both, key=lambda p: p.congestion, reverse=True)[:5]
    top_pm = sorted(with_both, key=lambda p: p.avg_pm25, reverse=True)[:5]

    return schemas.MapOut(points=points, correlation=corr, top_congestion=top_cong, top_pm25=top_pm)
