from fastapi import APIRouter, Depends, HTTPException
from database.models import (Delivery, DeliveryStatus, Warehouse, WarehouseStatus, Courier, CourierStatus,
                             CourierLocation, TrackingEvent, InventoryReservation, ReservationStatus, Route,
                             RouteStatus, RouteStop)
from database.schema import DeliveryInputSchema, DeliveryAssignSchema, DeliveryStatusSchema, DeliveryOutSchema
from api.dependencies import get_db, get_current_user
from api.courier import get_my_courier, update_courier_load
from api.reservation import finish_reservation
from clients.marketplace_services import get_order
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
import secrets

delivery_router = APIRouter(prefix='/deliveries', tags=['Deliveries'])

DELIVERY_STEPS = {
    DeliveryStatus.pending: [DeliveryStatus.assigned, DeliveryStatus.cancelled],
    DeliveryStatus.assigned: [DeliveryStatus.in_transit, DeliveryStatus.failed, DeliveryStatus.cancelled],
    DeliveryStatus.in_transit: [DeliveryStatus.delivered, DeliveryStatus.failed, DeliveryStatus.cancelled],
    DeliveryStatus.failed: [DeliveryStatus.assigned, DeliveryStatus.cancelled],
    DeliveryStatus.delivered: [],
    DeliveryStatus.cancelled: [],
}

DELIVERY_TEXT = {
    DeliveryStatus.pending: 'Доставка создана',
    DeliveryStatus.assigned: 'Курьер назначен',
    DeliveryStatus.in_transit: 'Курьер забрал заказ со склада',
    DeliveryStatus.delivered: 'Заказ доставлен',
    DeliveryStatus.failed: 'Не удалось доставить заказ',
    DeliveryStatus.cancelled: 'Доставка отменена',
}


def in_route(db: Session, delivery_id: int):
    return db.query(RouteStop).join(RouteStop.stop_route).filter(
        RouteStop.delivery_id == delivery_id,
        Route.status.in_([RouteStatus.planned, RouteStatus.active])).first() is not None


def change_delivery_status(delivery_db: Delivery, status: DeliveryStatus, db: Session,
                           latitude: Optional[float] = None, longitude: Optional[float] = None,
                           description: Optional[str] = None):
    if status not in DELIVERY_STEPS[delivery_db.status]:
        raise HTTPException(detail=f'Нельзя перейти из {delivery_db.status.value} в {status.value}',
                            status_code=400)

    if latitude is None or longitude is None:
        latitude, longitude = None, None
        if status in (DeliveryStatus.pending, DeliveryStatus.assigned):
            latitude = delivery_db.delivery_warehouse.latitude
            longitude = delivery_db.delivery_warehouse.longitude
        elif delivery_db.courier_id:
            location_db = db.query(CourierLocation).filter(
                CourierLocation.courier_id == delivery_db.courier_id).order_by(CourierLocation.id.desc()).first()
            if location_db:
                latitude, longitude = location_db.latitude, location_db.longitude

    delivery_db.status = status
    if status == DeliveryStatus.delivered:
        delivery_db.delivered_at = datetime.now(timezone.utc)

    db.add(TrackingEvent(delivery_id=delivery_db.id, status=status, latitude=latitude, longitude=longitude,
                         description=description or DELIVERY_TEXT[status]))

    if status in (DeliveryStatus.delivered, DeliveryStatus.cancelled):
        reservations = db.query(InventoryReservation).filter(
            InventoryReservation.order_id == delivery_db.order_id,
            InventoryReservation.status == ReservationStatus.active).all()
        for reservation_db in reservations:
            finish_reservation(reservation_db, ReservationStatus.committed if status == DeliveryStatus.delivered
                               else ReservationStatus.released)

    if delivery_db.delivery_courier:
        db.flush()
        update_courier_load(delivery_db.delivery_courier, db)


async def check_delivery(delivery: DeliveryInputSchema, db: Session, token: str, delivery_id: Optional[int] = None):
    warehouse_db = db.query(Warehouse).filter(Warehouse.id == delivery.warehouse_id).first()
    if not warehouse_db:
        raise HTTPException(detail='Склад не найден', status_code=400)

    if warehouse_db.status != WarehouseStatus.active:
        raise HTTPException(detail='Склад не работает', status_code=400)

    order = await get_order(delivery.order_id, token)
    if warehouse_db.city_id != order['city_id']:
        raise HTTPException(detail='Склад не в городе заказа', status_code=400)

    if db.query(Delivery).filter(Delivery.order_id == delivery.order_id, Delivery.id != delivery_id,
                                 Delivery.status != DeliveryStatus.cancelled).first():
        raise HTTPException(detail='На этот заказ доставка уже есть', status_code=400)


def get_delivery(delivery_id: int, db: Session):
    delivery_db = db.query(Delivery).filter(Delivery.id == delivery_id).first()
    if not delivery_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)
    return delivery_db


@delivery_router.post('/', response_model=DeliveryOutSchema)
async def create_delivery(delivery: DeliveryInputSchema, db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    await check_delivery(delivery, db, current_user['token'])
    tracking_code = f'GL{secrets.token_hex(4).upper()}'
    while db.query(Delivery).filter(Delivery.tracking_code == tracking_code).first():
        tracking_code = f'GL{secrets.token_hex(4).upper()}'

    delivery_db = Delivery(**delivery.model_dump(), tracking_code=tracking_code)
    db.add(delivery_db)
    db.flush()
    warehouse_db = db.query(Warehouse).filter(Warehouse.id == delivery.warehouse_id).first()
    db.add(TrackingEvent(delivery_id=delivery_db.id, status=DeliveryStatus.pending, latitude=warehouse_db.latitude,
                         longitude=warehouse_db.longitude, description=DELIVERY_TEXT[DeliveryStatus.pending]))
    db.commit()
    db.refresh(delivery_db)
    return delivery_db


@delivery_router.get('/', response_model=List[DeliveryOutSchema])
async def list_delivery(order_id: Optional[int] = None, status: Optional[DeliveryStatus] = None,
                        db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    query = db.query(Delivery)
    courier_db = db.query(Courier).filter(Courier.user_id == current_user['id']).first()
    if current_user['status'] != 'manager' and courier_db:
        query = query.filter(Delivery.courier_id == courier_db.id)
    elif current_user['status'] != 'manager':
        if order_id is None:
            raise HTTPException(detail='Укажите order_id своего заказа', status_code=400)
        await get_order(order_id, current_user['token'])

    if order_id is not None:
        query = query.filter(Delivery.order_id == order_id)
    if status is not None:
        query = query.filter(Delivery.status == status)
    return query.all()


@delivery_router.get('/{delivery_id}/', response_model=DeliveryOutSchema)
async def detail_delivery(delivery_id: int, db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    delivery_db = get_delivery(delivery_id, db)
    if current_user['status'] != 'manager' and delivery_db.courier_id != get_my_courier(db, current_user).id:
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    return delivery_db


@delivery_router.put('/{delivery_id}/', response_model=dict)
async def update_delivery(delivery_id: int, delivery: DeliveryInputSchema, db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    delivery_db = get_delivery(delivery_id, db)
    if delivery_db.status != DeliveryStatus.pending:
        raise HTTPException(detail='Менять можно только доставку без курьера', status_code=400)

    await check_delivery(delivery, db, current_user['token'], delivery_id)
    for delivery_key, delivery_value in delivery.model_dump().items():
        setattr(delivery_db, delivery_key, delivery_value)

    db.commit()
    db.refresh(delivery_db)
    return {'message': 'Доставка изменена'}


@delivery_router.delete('/{delivery_id}/', response_model=dict)
async def delete_delivery(delivery_id: int, db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    delivery_db = get_delivery(delivery_id, db)
    if delivery_db.status not in (DeliveryStatus.pending, DeliveryStatus.cancelled):
        raise HTTPException(detail='Сначала отмените доставку', status_code=400)

    db.delete(delivery_db)
    db.commit()
    return {'message': 'Доставка удалена'}


@delivery_router.post('/{delivery_id}/assign/', response_model=DeliveryOutSchema)
async def assign_delivery(delivery_id: int, assign: DeliveryAssignSchema, db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    delivery_db = get_delivery(delivery_id, db)
    courier_db = db.query(Courier).filter(Courier.id == assign.courier_id).first()
    if not courier_db:
        raise HTTPException(detail='Курьер не найден', status_code=400)

    if courier_db.warehouse_id != delivery_db.warehouse_id:
        raise HTTPException(detail='Курьер с другого склада', status_code=400)

    if delivery_db.courier_id == courier_db.id and delivery_db.status == DeliveryStatus.assigned:
        raise HTTPException(detail='Этот курьер уже назначен', status_code=400)

    if courier_db.status != CourierStatus.available:
        raise HTTPException(detail=f'Курьер сейчас {courier_db.status.value}', status_code=400)

    if in_route(db, delivery_id):
        raise HTTPException(detail='Доставка уже в маршруте', status_code=400)

    old_courier = delivery_db.delivery_courier
    delivery_db.delivery_courier = courier_db
    if delivery_db.status == DeliveryStatus.assigned:
        db.add(TrackingEvent(delivery_id=delivery_db.id, status=DeliveryStatus.assigned,
                             latitude=delivery_db.delivery_warehouse.latitude,
                             longitude=delivery_db.delivery_warehouse.longitude,
                             description='Назначен другой курьер'))
        db.flush()
        update_courier_load(old_courier, db)
        update_courier_load(courier_db, db)
    else:
        change_delivery_status(delivery_db, DeliveryStatus.assigned, db)

    db.commit()
    db.refresh(delivery_db)
    return delivery_db


@delivery_router.post('/{delivery_id}/status/', response_model=DeliveryOutSchema)
async def status_delivery(delivery_id: int, delivery_status: DeliveryStatusSchema, db: Session = Depends(get_db),
                          current_user: dict = Depends(get_current_user)):
    delivery_db = get_delivery(delivery_id, db)
    if current_user['status'] != 'manager':
        if delivery_db.courier_id != get_my_courier(db, current_user).id:
            raise HTTPException(detail='Недостаточно прав', status_code=403)
        if delivery_status.status == DeliveryStatus.cancelled:
            raise HTTPException(detail='Отменяет только менеджер', status_code=403)

    if delivery_status.status == DeliveryStatus.assigned:
        raise HTTPException(detail='Курьера назначают через /assign/', status_code=400)

    change_delivery_status(delivery_db, delivery_status.status, db, delivery_status.latitude,
                           delivery_status.longitude, delivery_status.description)
    db.commit()
    db.refresh(delivery_db)
    return delivery_db
