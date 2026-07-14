"""ORM 모델 정의.

- stations        : 인천 1호선 33개 역사 (좌표, 노선순서, PM2.5 측정소 보유 여부)
- pm25_hourly     : 2024년 10월 초미세먼지 1시간 평균값 (28개 측정소 x 744시간)
- traffic_hourly  : 2026년 4월 역/시간대별 통행량 (33개 역 x 승하차 x 20시간대)
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    line_order = Column(Integer, nullable=False)  # 노선상 순서 (0=검단호수공원 ... 32=송도달빛축제공원)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    has_pm25 = Column(Boolean, default=False)

    pm25_records = relationship("PM25Hourly", back_populates="station", cascade="all, delete-orphan")
    traffic_records = relationship("TrafficHourly", back_populates="station", cascade="all, delete-orphan")


class PM25Hourly(Base):
    __tablename__ = "pm25_hourly"
    __table_args__ = (UniqueConstraint("station_id", "ts", name="uq_pm25_station_ts"),)

    id = Column(Integer, primary_key=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True)
    ts = Column(DateTime, nullable=False, index=True)  # 2024-10-01 00:00 ~ 2024-10-31 23:00
    value = Column(Float, nullable=False)  # PM2.5 (㎍/㎥)

    station = relationship("Station", back_populates="pm25_records")


class TrafficHourly(Base):
    __tablename__ = "traffic_hourly"
    __table_args__ = (
        UniqueConstraint("station_id", "direction", "hour_index", "period_label",
                          name="uq_traffic_station_dir_hour_period"),
    )

    id = Column(Integer, primary_key=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True)
    direction = Column(String, nullable=False)      # '승차' / '하차'
    hour_label = Column(String, nullable=False)      # '05시' ... '24시이후'
    hour_index = Column(Integer, nullable=False)     # 0..19
    count = Column(Integer, nullable=False)
    period_label = Column(String, nullable=False, default="2026-04")

    station = relationship("Station", back_populates="traffic_records")
