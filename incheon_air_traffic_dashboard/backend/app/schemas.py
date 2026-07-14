from typing import List, Optional
from pydantic import BaseModel


class StationOut(BaseModel):
    name: str
    line_order: int
    lat: float
    lon: float
    has_pm25: bool

    class Config:
        from_attributes = True


class PM25SeriesOut(BaseModel):
    station: str
    labels: List[str]      # "MM-DD HH"
    values: List[float]


class ForecastOut(BaseModel):
    station: str
    model: str                     # "seasonal" | "linear"
    hist_labels: List[str]
    hist_values: List[float]
    forecast_labels: List[str]
    forecast_values: List[float]
    note: str
    stat_avg: float
    stat_max: float
    stat_min: float
    stat_over35_hours: int
    stat_over35_ratio: float
    stat_forecast_avg: float


class CrossOut(BaseModel):
    station: str
    hour_labels: List[str]
    pm_aligned: List[float]
    traffic_total: List[int]
    correlation: float


class ScatterPointOut(BaseModel):
    station: str
    avg_pm25: float
    total_traffic: int


class ScatterOut(BaseModel):
    points: List[ScatterPointOut]
    correlation: float


class MapPointOut(BaseModel):
    station: str
    lat: float
    lon: float
    avg_pm25: Optional[float]
    congestion: Optional[int]


class MapOut(BaseModel):
    points: List[MapPointOut]
    correlation: float
    top_congestion: List[MapPointOut]
    top_pm25: List[MapPointOut]
