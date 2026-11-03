from fastapi import APIRouter, Depends, HTTPException
from database.models import CourierLocation
from database.schema import CourierLocationInputSchema, CourierLocationOutSchema
from api.dependencies import get_db, get_current_user
from api.courier import get_my_courier
from typing import List, Optional
from sqlalchemy.orm import Session

courier_location_router = APIRouter(prefix='/courier-locations', tags=['Courier Locations'])


@courier_location_router.post('/', response_model=CourierLocationOutSchema)
async def create_courier_location(location: CourierLocationInputSchema, db: Session = Depends(get_db),
                                  current_user: dict = Depends(get_current_user)):
    courier_db = get_my_courier(db, current_user)
    location_db = CourierLocation(**location.model_dump(), courier_id=courier_db.id)
    db.add(location_db)
    db.commit()
    db.refresh(location_db)
    return location_db


@courier_location_router.get('/', response_model=List[CourierLocationOutSchema])
async def list_courier_location(courier_id: Optional[int] = None, limit: int = 50, db: Session = Depends(get_db),
                                current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        courier_db = get_my_courier(db, current_user)
        if courier_id is not None and courier_id != courier_db.id:
            raise HTTPException(detail='Недостаточно прав', status_code=403)
        courier_id = courier_db.id

    query = db.query(CourierLocation)
    if courier_id is not None:
        query = query.filter(CourierLocation.courier_id == courier_id)
    return query.order_by(CourierLocation.id.desc()).limit(limit).all()
