from fastapi import APIRouter, Depends, HTTPException
from database.models import RouteStop, StopType, StopStatus, RouteStatus, DeliveryStatus, TrackingEvent
from database.schema import RouteStopStatusSchema, RouteStopOutSchema
from api.dependencies import get_db, get_current_user
from api.courier import get_my_courier
from api.delivery import change_delivery_status
from datetime import datetime, timezone
from sqlalchemy.orm import Session

route_stop_router = APIRouter(prefix='/route-stops', tags=['Route Stops'])


@route_stop_router.post('/{stop_id}/status/', response_model=RouteStopOutSchema)
async def status_route_stop(stop_id: int, stop_status: RouteStopStatusSchema, db: Session = Depends(get_db),
                            current_user: dict = Depends(get_current_user)):
    courier_db = get_my_courier(db, current_user)
    stop_db = db.query(RouteStop).filter(RouteStop.id == stop_id).first()
    if not stop_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    route_db = stop_db.stop_route
    if route_db.courier_id != courier_db.id:
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    if route_db.status != RouteStatus.active:
        raise HTTPException(detail='Маршрут не активен', status_code=400)

    if stop_db.status in (StopStatus.completed, StopStatus.skipped):
        raise HTTPException(detail='Точка уже пройдена', status_code=400)

    if stop_status.status in (StopStatus.pending, stop_db.status):
        raise HTTPException(detail=f'Нельзя поставить {stop_status.status.value}', status_code=400)

    delivery_db = stop_db.stop_delivery
    point = (stop_db.latitude, stop_db.longitude)
    if stop_db.stop_type == StopType.pickup:
        if stop_status.status == StopStatus.completed and delivery_db.status == DeliveryStatus.assigned:
            change_delivery_status(delivery_db, DeliveryStatus.in_transit, db, *point)
    elif stop_status.status == StopStatus.arrived and delivery_db.status == DeliveryStatus.in_transit:
        db.add(TrackingEvent(delivery_id=delivery_db.id, status=delivery_db.status, latitude=stop_db.latitude,
                             longitude=stop_db.longitude, description='Курьер прибыл по адресу'))
    elif stop_status.status == StopStatus.completed:
        if delivery_db.status == DeliveryStatus.assigned:
            raise HTTPException(detail='Сначала заберите заказ на складе', status_code=400)
        if delivery_db.status == DeliveryStatus.in_transit:
            change_delivery_status(delivery_db, DeliveryStatus.delivered, db, *point)
    elif stop_status.status == StopStatus.skipped and delivery_db.status in (DeliveryStatus.assigned,
                                                                              DeliveryStatus.in_transit):
        change_delivery_status(delivery_db, DeliveryStatus.failed, db, *point, 'Курьер не смог доставить заказ')

    now = datetime.now(timezone.utc)
    if stop_status.status in (StopStatus.arrived, StopStatus.completed) and stop_db.arrived_at is None:
        stop_db.arrived_at = now
    stop_db.status = stop_status.status

    if all(route_stop.status in (StopStatus.completed, StopStatus.skipped) for route_stop in route_db.route_stop):
        route_db.status = RouteStatus.completed
        route_db.completed_at = now

    db.commit()
    db.refresh(stop_db)
    return stop_db
