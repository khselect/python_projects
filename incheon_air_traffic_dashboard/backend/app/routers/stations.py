from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/api/stations", tags=["stations"])


@router.get("", response_model=list[schemas.StationOut])
def list_stations(db: Session = Depends(get_db)):
    return crud.get_all_stations(db)


periods_router = APIRouter(prefix="/api/periods", tags=["periods"])


@periods_router.get("", response_model=list[str])
def list_periods(db: Session = Depends(get_db)):
    """적재된 통행량 기준월(period_label) 목록."""
    return crud.get_available_periods(db)
