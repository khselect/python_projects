"""HTML 프로토타입에서 추출한 merged_dataset.json 을 PostgreSQL로 적재하는 ETL.

원본 엑셀이 없는 환경(맥미니)에서 사용. 데이터 구조는 프로토타입 HTML의
data-slot JSON과 동일하며, load_data.py(엑셀 ETL)와 같은 테이블에 같은 형태로 적재한다.

사용법:
    python -m etl.load_from_json --json /data/merged_dataset.json

JSON 구조:
  pm25:    {hours: ["MM-DD HH" x744], stations: {역명: [744개 값]}}   # 2024년 10월
  traffic: {hourLabels: ["05시"..."24시이후"], stations: {역명: {승차:{total,hourly}, 하차:{...}}}}
  coords:  {역명: [lat, lon]}
  line1Order: [33개 역, 노선 순서]
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal, Base
from app import models

PM25_YEAR = 2024  # PM.hours 는 "MM-DD HH" 형식이라 연도 정보가 없음 (프로토타입 기준 2024년 10월 고정)


def load(json_path: str, period_label: str = "2026-04"):
    Base.metadata.create_all(bind=engine)

    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    pm25 = data["pm25"]
    traffic = data["traffic"]
    coords = data["coords"]
    line_order_names = data["line1Order"]
    hour_labels = traffic["hourLabels"]

    db: Session = SessionLocal()
    try:
        db.query(models.PM25Hourly).delete()
        db.query(models.TrafficHourly).delete()
        db.query(models.Station).delete()
        db.commit()

        station_objs: dict[str, models.Station] = {}
        for idx, name in enumerate(line_order_names):
            lat, lon = coords.get(name, (0.0, 0.0))
            st = models.Station(
                name=name, line_order=idx, lat=lat, lon=lon,
                has_pm25=name in pm25["stations"],
            )
            db.add(st)
            station_objs[name] = st
        db.commit()

        pm_count = 0
        for name, values in pm25["stations"].items():
            st = station_objs.get(name)
            if st is None:
                continue
            for hour_str, val in zip(pm25["hours"], values):
                if val is None:
                    continue
                md, hh = hour_str.split(" ")
                mm, dd = md.split("-")
                ts = dt.datetime(PM25_YEAR, int(mm), int(dd), int(hh))
                db.add(models.PM25Hourly(station_id=st.id, ts=ts, value=float(val)))
                pm_count += 1
        db.commit()

        tr_count = 0
        for name, directions in traffic["stations"].items():
            st = station_objs.get(name)
            if st is None:
                continue
            for direction, payload in directions.items():
                for h_idx, (label, cnt) in enumerate(zip(hour_labels, payload["hourly"])):
                    db.add(models.TrafficHourly(
                        station_id=st.id, direction=direction, hour_label=label,
                        hour_index=h_idx, count=int(cnt), period_label=period_label,
                    ))
                    tr_count += 1
        db.commit()

        print(f"적재 완료: 역 {len(station_objs)}개, PM2.5 레코드 {pm_count}건, 통행량 레코드 {tr_count}건")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="merged_dataset.json → PostgreSQL 적재")
    parser.add_argument("--json", required=True, help="merged_dataset.json 경로")
    parser.add_argument("--period", default="2026-04", help="통행량 자료 기준 년월 라벨")
    args = parser.parse_args()
    load(args.json, args.period)
