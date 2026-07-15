"""DB 조회 헬퍼 함수."""
from __future__ import annotations
import datetime as dt
from typing import Dict, List, Optional, Tuple
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from . import models


def get_all_stations(db: Session) -> List[models.Station]:
    return db.execute(select(models.Station).order_by(models.Station.line_order)).scalars().all()


def get_station_by_name(db: Session, name: str) -> Optional[models.Station]:
    return db.execute(select(models.Station).where(models.Station.name == name)).scalar_one_or_none()


def get_pm25_records(db: Session, station_id: int, start_day: int, end_day: int,
                      month: Optional[str] = None) -> List[Tuple[dt.datetime, float]]:
    """month('YYYY-MM') 지정 시 해당 월만, 미지정 시 누적 전체 기간을 반환."""
    q = (
        select(models.PM25Hourly.ts, models.PM25Hourly.value)
        .where(models.PM25Hourly.station_id == station_id)
        .order_by(models.PM25Hourly.ts)
    )
    rows = db.execute(q).all()
    return [(ts, val) for ts, val in rows
            if start_day <= ts.day <= end_day
            and (month is None or ts.strftime("%Y-%m") == month)]


def get_pm25_months(db: Session) -> List[str]:
    """적재된 PM2.5 데이터의 월('YYYY-MM') 목록 (오름차순)."""
    rows = db.execute(
        select(extract("year", models.PM25Hourly.ts),
               extract("month", models.PM25Hourly.ts)).distinct()
    ).all()
    return sorted(f"{int(y):04d}-{int(m):02d}" for y, m in rows)


def get_dataset_summary(db: Session) -> Dict[str, List[Dict]]:
    """업로드/적재된 데이터셋 현황 — 통행량 기준월별, PM2.5 월별 레코드·역 수."""
    traffic_rows = db.execute(
        select(models.TrafficHourly.period_label,
               func.count(models.TrafficHourly.id),
               func.count(func.distinct(models.TrafficHourly.station_id)))
        .group_by(models.TrafficHourly.period_label)
        .order_by(models.TrafficHourly.period_label)
    ).all()
    pm_rows = db.execute(
        select(extract("year", models.PM25Hourly.ts).label("y"),
               extract("month", models.PM25Hourly.ts).label("m"),
               func.count(models.PM25Hourly.id),
               func.count(func.distinct(models.PM25Hourly.station_id)))
        .group_by("y", "m").order_by("y", "m")
    ).all()
    return {
        "traffic": [{"period": p, "records": n, "stations": s} for p, n, s in traffic_rows],
        "pm25": [{"month": f"{int(y):04d}-{int(m):02d}", "records": n, "stations": s}
                  for y, m, n, s in pm_rows],
    }


def get_pm25_all(db: Session, station_id: int) -> List[Tuple[dt.datetime, float]]:
    q = (
        select(models.PM25Hourly.ts, models.PM25Hourly.value)
        .where(models.PM25Hourly.station_id == station_id)
        .order_by(models.PM25Hourly.ts)
    )
    return list(db.execute(q).all())


def get_pm25_hour_avg(db: Session, station_id: int) -> Dict[int, float]:
    """전체 기간 시간대(0-23)별 평균."""
    records = get_pm25_all(db, station_id)
    buckets: Dict[int, List[float]] = {h: [] for h in range(24)}
    for ts, v in records:
        buckets[ts.hour].append(v)
    return {h: (sum(vs) / len(vs) if vs else 0.0) for h, vs in buckets.items()}


def get_available_periods(db: Session) -> List[str]:
    """적재된 통행량 기준월(period_label) 목록 (오름차순)."""
    rows = db.execute(
        select(models.TrafficHourly.period_label).distinct()
        .order_by(models.TrafficHourly.period_label)
    ).scalars().all()
    return list(rows)


def get_traffic(db: Session, station_id: int, period: Optional[str] = None) -> Dict[str, Dict]:
    """방향별 {hour_labels, hourly(list), total} 딕셔너리.

    period 미지정 시 가장 최근 기준월 데이터를 사용한다.
    (여러 달이 적재된 상태에서 필터 없이 조회하면 시간대 배열이 달 수만큼
     늘어나 그래프가 깨지므로 반드시 한 달로 한정한다.)
    """
    if period is None:
        periods = get_available_periods(db)
        if not periods:
            return {}
        period = periods[-1]
    q = (
        select(models.TrafficHourly)
        .where(models.TrafficHourly.station_id == station_id,
               models.TrafficHourly.period_label == period)
        .order_by(models.TrafficHourly.direction, models.TrafficHourly.hour_index)
    )
    rows = db.execute(q).scalars().all()
    out: Dict[str, Dict] = {}
    for r in rows:
        d = out.setdefault(r.direction, {"hour_labels": [], "hourly": []})
        d["hour_labels"].append(r.hour_label)
        d["hourly"].append(r.count)
    for d in out.values():
        d["total"] = sum(d["hourly"])
    return out


def get_traffic_total(db: Session, station_id: int, period: Optional[str] = None) -> int:
    tr = get_traffic(db, station_id, period)
    return sum(d["total"] for d in tr.values())
