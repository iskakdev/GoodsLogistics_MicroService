from fastapi import APIRouter, Depends, HTTPException
from database.models import Delivery
from database.schema import TrackingOutSchema
from api.dependencies import get_db
from sqlalchemy.orm import Session

tracking_router = APIRouter(prefix='/tracking', tags=['Tracking'])


@tracking_router.get('/{tracking_code}/', response_model=TrackingOutSchema)
async def detail_tracking(tracking_code: str, db: Session = Depends(get_db)):
    delivery_db = db.query(Delivery).filter(Delivery.tracking_code == tracking_code.upper()).first()
    if not delivery_db:
        raise HTTPException(detail='Трек-номер не найден', status_code=400)

    return delivery_db
