"""과제1: 역사별 시간대별 초미세먼지 추세 · 기간예측 API"""
import datetime as dt
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import crud, schemas, analysis
from ..database import get_db

router = APIRouter(prefix="/api/trend", tags=["trend"])


@router.get("/forecast", response_model=schemas.ForecastOut)
def forecast(
    station: str,
    start_day: int = Query(1, ge=1, le=31),
    end_day: int = Query(31, ge=1, le=31),
    model: str = Query("seasonal", pattern="^(seasonal|linear)$"),
    horizon_days: int = Query(7, ge=1, le=30),
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$",
                               description="PM2.5 기준월(YYYY-MM). 미지정 시 누적 전체 기간 사용"),
    db: Session = Depends(get_db),
):
    st = crud.get_station_by_name(db, station)
    if st is None or not st.has_pm25:
        raise HTTPException(404, f"'{station}' 역은 PM2.5 측정소 데이터가 없습니다.")
    if start_day > end_day:
        raise HTTPException(400, "start_day는 end_day보다 작거나 같아야 합니다.")

    records = crud.get_pm25_records(db, st.id, start_day, end_day, month)
    if not records:
        raise HTTPException(404, "해당 기간의 데이터가 없습니다.")

    hist_labels = [ts.strftime("%m-%d %H") for ts, _ in records]
    hist_values = [v for _, v in records]
    last_ts = records[-1][0]

    if model == "seasonal":
        f_labels, f_values, note, grand = analysis.seasonal_forecast(records, last_ts, horizon_days)
    else:
        f_labels, f_values, note, grand = analysis.linear_forecast(records, last_ts, horizon_days)

    over35 = sum(1 for v in hist_values if v > 35)
    return schemas.ForecastOut(
        station=station,
        model=model,
        hist_labels=hist_labels,
        hist_values=hist_values,
        forecast_labels=f_labels,
        forecast_values=f_values,
        note=note,
        stat_avg=sum(hist_values) / len(hist_values),
        stat_max=max(hist_values),
        stat_min=min(hist_values),
        stat_over35_hours=over35,
        stat_over35_ratio=100.0 * over35 / len(hist_values),
        stat_forecast_avg=sum(f_values) / len(f_values) if f_values else 0.0,
    )
