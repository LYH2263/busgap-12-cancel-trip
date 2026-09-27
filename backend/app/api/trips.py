from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Trip
router = APIRouter(prefix="/trips", tags=["trips"])

def trip_dict(t: Trip) -> dict:
    return {"id": t.id, "line_id": t.line_id, "trip_no": t.trip_no,
            "planned_depart": t.planned_depart.isoformat(), "vehicle_no": t.vehicle_no,
            "status": t.status}

@router.get("")
def list_trips(line_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Trip).order_by(Trip.planned_depart)
    if line_id is not None: q = q.where(Trip.line_id == line_id)
    return [trip_dict(r) for r in db.scalars(q).all()]

@router.post("/{trip_id}/cancel")
def cancel_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = db.get(Trip, trip_id)
    if not trip: raise HTTPException(404, "班次不存在")
    # 幂等：已取消的班次保持取消，不再写入任何到站记录，也不触碰其它班次
    if trip.status != "cancelled":
        trip.status = "cancelled"
        db.commit()
        db.refresh(trip)
    return trip_dict(trip)
