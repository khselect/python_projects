"""DB 조회 헬퍼 함수."""
from __future__ import annotations
import datetime as dt
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def get_all_stations(db: Session) -> List[models.Station]:
    return db.execute(select(models.Station).order_by(models.Station.line_order)).scalars().all()


def get_station_by_name(db: Session, name: str) -> Optional[models.Station]:
    return db.execute(select(models.Station).where(models.Station.name == name)).scalar_one_or_none()


def get_pm25_records(db: Session, station_id: int,
                      start_day: int, end_day: int) -> List[Tuple[dt.datetime, float]]:
    q = (
        select(models.PM25Hourly.ts, models.PM25Hourly.value)
        .where(models.PM25Hourly.station_id == station_id)
        .order_by(models.PM25Hourly.ts)
    )
    rows = db.execute(q).all()
    return [(ts, val) for ts, val in rows if start_day <= ts.day <= end_day]


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


def get_traffic(db: Session, station_id: int) -> Dict[str, Dict]:
    """방향별 {hour_labels, hourly(list), total} 딕셔너리."""
    q = (
        select(models.TrafficHourly)
        .where(models.TrafficHourly.station_id == station_id)
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


def get_traffic_total(db: Session, station_id: int) -> int:
    tr = get_traffic(db, station_id)
    return sum(d["total"] for d in tr.values())
