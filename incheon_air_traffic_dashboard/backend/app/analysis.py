"""통계/예측 로직.

HTML 프로토타입(대시보드.html)의 JS 로직을 Python으로 포팅한 것으로,
- 계절성 분해(요일×시간대 가법 분해) 예측
- 선형회귀(일평균 추세선) 예측
- 시간대 정렬(초미세먼지 0~23시 ↔ 통행량 05시~24시이후 20구간) 및 상관계수 계산
을 담당한다.
"""
from __future__ import annotations
import datetime as dt
from typing import Dict, List, Tuple
import numpy as np


def pearson(x: List[float], y: List[float]) -> float:
    if len(x) < 2 or len(x) != len(y):
        return 0.0
    xa, ya = np.array(x, dtype=float), np.array(y, dtype=float)
    if xa.std() == 0 or ya.std() == 0:
        return 0.0
    return float(np.corrcoef(xa, ya)[0, 1])


def hour_effects_and_grand(records: List[Tuple[dt.datetime, float]]) -> Tuple[float, Dict[int, float], Dict[int, float]]:
    """선택 구간 records=[(ts, value), ...] 로부터
    전체평균, 시간대(0-23) 효과, 요일(0=월..6=일) 효과를 가법 분해로 산출."""
    values = [v for _, v in records]
    grand = float(np.mean(values)) if values else 0.0

    hour_buckets: Dict[int, List[float]] = {h: [] for h in range(24)}
    dow_buckets: Dict[int, List[float]] = {d: [] for d in range(7)}
    for ts, v in records:
        hour_buckets[ts.hour].append(v)
        dow_buckets[ts.weekday()].append(v)

    hour_eff = {h: (float(np.mean(vs)) - grand if vs else 0.0) for h, vs in hour_buckets.items()}
    dow_eff = {d: (float(np.mean(vs)) - grand if vs else 0.0) for d, vs in dow_buckets.items()}
    return grand, hour_eff, dow_eff


def seasonal_forecast(records: List[Tuple[dt.datetime, float]], last_ts: dt.datetime,
                       horizon_days: int) -> Tuple[List[str], List[float], str, float]:
    """계절성 분해(요일×시간대 패턴) 기반 예측.
    반환: (라벨 리스트, 값 리스트, 설명문, 구간전체평균)"""
    grand, hour_eff, dow_eff = hour_effects_and_grand(records)
    labels, values = [], []
    for d in range(1, horizon_days + 1):
        day = last_ts.date() + dt.timedelta(days=d)
        for h in range(24):
            ts = dt.datetime.combine(day, dt.time(hour=h))
            pred = max(0.0, grand + dow_eff.get(ts.weekday(), 0.0) + hour_eff.get(h, 0.0))
            labels.append(ts.strftime("%m-%d %H"))
            values.append(pred)
    note = (f"요일×시간대 평균 패턴 기반 예측입니다. 구간 전체평균 {grand:.1f}㎍/㎥에 "
            f"요일효과·시간대효과를 더해 향후 {horizon_days}일을 추정합니다.")
    return labels, values, note, grand


def linear_forecast(records: List[Tuple[dt.datetime, float]], last_ts: dt.datetime,
                     horizon_days: int) -> Tuple[List[str], List[float], str, float]:
    """선택 구간의 일평균 시계열에 최소자승 선형회귀를 적합해 향후 horizon_days일을 예측."""
    by_day: Dict[dt.date, List[float]] = {}
    for ts, v in records:
        by_day.setdefault(ts.date(), []).append(v)
    days_sorted = sorted(by_day.keys())
    day_avgs = [float(np.mean(by_day[d])) for d in days_sorted]

    n = len(day_avgs)
    if n < 2:
        a, b = (day_avgs[0] if day_avgs else 0.0), 0.0
    else:
        xs = np.arange(n, dtype=float)
        ys = np.array(day_avgs, dtype=float)
        b, a = np.polyfit(xs, ys, 1)  # slope, intercept

    labels, values = [], []
    for d in range(1, horizon_days + 1):
        x = n - 1 + d
        pred_day_avg = max(0.0, a + b * x)
        day = last_ts.date() + dt.timedelta(days=d)
        for h in range(24):
            ts = dt.datetime.combine(day, dt.time(hour=h))
            labels.append(ts.strftime("%m-%d %H"))
            values.append(pred_day_avg)

    note = (f"선택 구간의 일평균 추세선 기울기는 하루당 {'+' if b>=0 else ''}{b:.2f}㎍/㎥ 입니다. "
            f"이 추세를 향후 {horizon_days}일 연장한 예측입니다.")
    grand = float(np.mean(day_avgs)) if day_avgs else 0.0
    return labels, values, note, grand


def align_pm_to_traffic_buckets(pm_hour_avg: Dict[int, float], hour_labels: List[str]) -> List[float]:
    """PM2.5 0~23시 평균(dict)을 통행량 시간라벨(05시..23시,24시이후) 순서로 정렬.
    '24시이후'는 심야~자정 구간 근사치로 0시 평균을 대응시킨다."""
    out = []
    for lbl in hour_labels:
        if lbl == "24시이후":
            out.append(pm_hour_avg.get(0, 0.0))
        else:
            h = int(lbl.replace("시", ""))
            out.append(pm_hour_avg.get(h, 0.0))
    return out
