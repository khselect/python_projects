from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/api/stations", tags=["stations"])


@router.get("", response_model=list[schemas.StationOut])
def list_stations(db: Session = Depends(get_db)):
    return crud.get_all_stations(db)
