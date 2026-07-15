"""데이터 업로드 API — 통행량/초미세먼지 엑셀을 웹에서 업로드해 DB에 누적 적재.

- POST /api/upload/traffic : 역·시간대별 통행량 xlsx + 기준월(YYYY-MM).
  같은 기준월은 교체, 다른 기준월은 누적된다.
- POST /api/upload/pm25    : 초미세먼지 월보 xlsx (공단양식 시트).
  측정시간(YYYYMMDDHH)에서 월을 자동 인식하며 해당 월 데이터만 교체, 다른 월은 누적.
- GET  /api/datasets       : 적재된 데이터셋 현황(월별 레코드·역 수) 목록.

원본 파일은 /data/uploads/ 에 보관한다 (docker-compose에서 ./data 를 rw로 마운트).
"""
from __future__ import annotations
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import extract
from sqlalchemy.orm import Session

from etl.load_data import LINE1_COORDS, parse_pm25, parse_traffic

from .. import crud, models
from ..database import get_db

router = APIRouter(prefix="/api", tags=["upload"])

UPLOAD_DIR = Path("/data/uploads")
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _save_upload(file: UploadFile, prefix: str) -> Path:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "xlsx 형식의 엑셀 파일만 업로드할 수 있습니다.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / f"{prefix}_{safe_name}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return dest


def _ensure_stations(db: Session, line_order_names: list[str] | None = None) -> dict[str, models.Station]:
    """stations 테이블이 비어 있으면 생성. line_order_names(통행량 엑셀 등장 순서)가
    없으면 LINE1_COORDS 정의 순서를 노선 순서로 사용."""
    station_objs = {s.name: s for s in db.query(models.Station).all()}
    if station_objs:
        return station_objs
    names = line_order_names or list(LINE1_COORDS.keys())
    for idx, name in enumerate(names):
        lat, lon = LINE1_COORDS.get(name, (0.0, 0.0))
        st = models.Station(name=name, line_order=idx, lat=lat, lon=lon, has_pm25=False)
        db.add(st)
        station_objs[name] = st
    db.flush()
    return station_objs


@router.post("/upload/traffic")
def upload_traffic(
    period: str = Form(..., description="자료 기준월 (예: 2026-06)"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not PERIOD_RE.match(period):
        raise HTTPException(400, "기준월은 YYYY-MM 형식이어야 합니다 (예: 2026-06).")
    path = _save_upload(file, f"통행량_{period}")

    try:
        hour_labels, traffic = parse_traffic(str(path))
    except KeyError:
        raise HTTPException(400, "엑셀에 '1호선 ' 시트가 없습니다. 역·시간대별 통행량 원본 양식인지 확인하세요.")
    except Exception as e:
        raise HTTPException(400, f"엑셀 파싱 실패: {e}")

    if not traffic:
        raise HTTPException(400, "통행량 데이터를 찾지 못했습니다. 원본 양식을 확인하세요.")
    last = traffic.get("송도달빛축제공원", {}).get("하차")
    if last and sum(last) >= 1_000_000:
        raise HTTPException(400, "송도달빛축제공원 하차 합계가 비정상적으로 큽니다 — '1호선 계' 행 오염 가능성.")

    station_objs = _ensure_stations(db, list(traffic.keys()))

    db.query(models.TrafficHourly).filter(
        models.TrafficHourly.period_label == period).delete()

    tr_count, skipped = 0, []
    for name, directions in traffic.items():
        st = station_objs.get(name)
        if st is None:
            skipped.append(name)
            continue
        for direction, hourly in directions.items():
            for h_idx, (label, cnt) in enumerate(zip(hour_labels, hourly)):
                db.add(models.TrafficHourly(
                    station_id=st.id, direction=direction, hour_label=label,
                    hour_index=h_idx, count=cnt, period_label=period,
                ))
                tr_count += 1
    db.commit()
    return {"type": "traffic", "period": period, "records": tr_count,
            "stations": len(traffic), "skipped_stations": skipped,
            "saved_as": path.name}


@router.post("/upload/pm25")
def upload_pm25(file: UploadFile = File(...), db: Session = Depends(get_db)):
    path = _save_upload(file, "초미세먼지")

    try:
        pm25 = parse_pm25(str(path))
    except KeyError:
        raise HTTPException(400, "엑셀에 '공단양식' 시트가 없습니다. 초미세먼지 월보 원본 양식인지 확인하세요.")
    except Exception as e:
        raise HTTPException(400, f"엑셀 파싱 실패: {e}")

    if not pm25:
        raise HTTPException(400, "PM2.5 데이터를 찾지 못했습니다. 원본 양식을 확인하세요.")

    months = sorted({ts.strftime("%Y-%m") for recs in pm25.values() for ts, _ in recs})
    station_objs = _ensure_stations(db)

    # 업로드 파일에 포함된 월의 기존 데이터만 교체 (다른 월은 유지 = 누적)
    for m in months:
        y, mm = m.split("-")
        db.query(models.PM25Hourly).filter(
            extract("year", models.PM25Hourly.ts) == int(y),
            extract("month", models.PM25Hourly.ts) == int(mm),
        ).delete(synchronize_session=False)

    pm_count, skipped = 0, []
    for name, records in pm25.items():
        st = station_objs.get(name)
        if st is None:
            skipped.append(name)
            continue
        if not st.has_pm25:
            st.has_pm25 = True
        for ts, val in records:
            db.add(models.PM25Hourly(station_id=st.id, ts=ts, value=val))
            pm_count += 1
    db.commit()
    return {"type": "pm25", "months": months, "records": pm_count,
            "stations": len(pm25) - len(skipped), "skipped_stations": skipped,
            "saved_as": path.name}


@router.get("/datasets")
def datasets(db: Session = Depends(get_db)):
    return crud.get_dataset_summary(db)
