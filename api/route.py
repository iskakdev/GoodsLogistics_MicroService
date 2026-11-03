from fastapi import APIRouter, Depends, HTTPException
from database.models import Route, RouteStatus, RouteStop, StopType, Courier, CourierStatus, Delivery, DeliveryStatus
from database.schema import RouteInputSchema, RouteOutSchema
from api.dependencies import get_db, get_current_user
from api.courier import get_my_courier
from api.delivery import in_route
from config import TRANSPORT_SPEED
from datetime import datetime, timedelta, timezone
from math import radians, sin, cos, asin, sqrt, ceil
from typing import List, Optional
from sqlalchemy.orm import Session

route_router = APIRouter(prefix='/routes', tags=['Routes'])


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float):
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def get_route(route_id: int, db: Session, current_user: dict):
    route_db = db.query(Route).filter(Route.id == route_id).first()
    if not route_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    if current_user['status'] != 'manager' and route_db.route_courier.user_id != current_user['id']:
        raise HTTPException(detail='Недостаточно прав', status_code=403)
    return route_db


@route_router.post('/', response_model=RouteOutSchema)
async def create_route(route: RouteInputSchema, db: Session = Depends(get_db),
                       current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    courier_db = db.query(Courier).filter(Courier.id == route.courier_id).first()
    if not courier_db:
        raise HTTPException(detail='Курьер не найден', status_code=400)

    if len(set(route.delivery_ids)) != len(route.delivery_ids):
        raise HTTPException(detail='Доставки повторяются', status_code=400)

    deliveries = []
    for delivery_id in route.delivery_ids:
        delivery_db = db.query(Delivery).filter(Delivery.id == delivery_id).first()
        if not delivery_db:
            raise HTTPException(detail=f'Доставка {delivery_id} не найдена', status_code=400)
        if delivery_db.courier_id != courier_db.id or delivery_db.status != DeliveryStatus.assigned:
            raise HTTPException(detail=f'Доставка {delivery_id} не назначена этому курьеру', status_code=400)
        if in_route(db, delivery_id):
            raise HTTPException(detail=f'Доставка {delivery_id} уже в маршруте', status_code=400)
        deliveries.append(delivery_db)

    warehouse_db = courier_db.courier_warehouse
    point = (warehouse_db.latitude, warehouse_db.longitude)
    stops = [RouteStop(delivery_id=delivery_db.id, stop_type=StopType.pickup, sequence=number,
                       latitude=warehouse_db.latitude, longitude=warehouse_db.longitude)
             for number, delivery_db in enumerate(deliveries, start=1)]

    total_distance = 0
    while deliveries:
        nearest = min(deliveries, key=lambda delivery_db: distance_km(
            *point, delivery_db.destination_latitude, delivery_db.destination_longitude))
        total_distance += distance_km(*point, nearest.destination_latitude, nearest.destination_longitude)
        point = (nearest.destination_latitude, nearest.destination_longitude)
        stops.append(RouteStop(delivery_id=nearest.id, stop_type=StopType.dropoff, sequence=len(stops) + 1,
                               latitude=nearest.destination_latitude, longitude=nearest.destination_longitude))
        deliveries.remove(nearest)

    speed = TRANSPORT_SPEED[courier_db.transport_type.value]
    route_db = Route(courier_id=courier_db.id, total_distance_km=round(total_distance, 2),
                     estimated_duration_min=ceil(total_distance / speed * 60), route_stop=stops)
    db.add(route_db)
    db.commit()
    db.refresh(route_db)
    return route_db


@route_router.get('/', response_model=List[RouteOutSchema])
async def list_route(courier_id: Optional[int] = None, status: Optional[RouteStatus] = None,
                     db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        courier_id = get_my_courier(db, current_user).id

    query = db.query(Route)
    if courier_id is not None:
        query = query.filter(Route.courier_id == courier_id)
    if status is not None:
        query = query.filter(Route.status == status)
    return query.all()


@route_router.get('/{route_id}/', response_model=RouteOutSchema)
async def detail_route(route_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_route(route_id, db, current_user)


@route_router.post('/{route_id}/start/', response_model=RouteOutSchema)
async def start_route(route_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    courier_db = get_my_courier(db, current_user)
    route_db = get_route(route_id, db, current_user)
    if courier_db.status == CourierStatus.suspended:
        raise HTTPException(detail='Вы отстранены', status_code=403)

    if route_db.status != RouteStatus.planned:
        raise HTTPException(detail=f'Маршрут уже {route_db.status.value}', status_code=400)

    if db.query(Route).filter(Route.courier_id == courier_db.id, Route.status == RouteStatus.active).first():
        raise HTTPException(detail='У вас уже есть активный маршрут', status_code=400)

    now = datetime.now(timezone.utc)
    route_db.status = RouteStatus.active
    route_db.started_at = now

    speed = TRANSPORT_SPEED[courier_db.transport_type.value]
    point = (courier_db.courier_warehouse.latitude, courier_db.courier_warehouse.longitude)
    passed_distance = 0
    for stop_db in route_db.route_stop:
        passed_distance += distance_km(*point, stop_db.latitude, stop_db.longitude)
        point = (stop_db.latitude, stop_db.longitude)
        delivery_db = stop_db.stop_delivery
        if stop_db.stop_type == StopType.dropoff and delivery_db.status in (DeliveryStatus.assigned,
                                                                            DeliveryStatus.in_transit):
            delivery_db.estimated_delivery_at = now + timedelta(minutes=passed_distance / speed * 60)

    db.commit()
    db.refresh(route_db)
    return route_db


@route_router.post('/{route_id}/cancel/', response_model=RouteOutSchema)
async def cancel_route(route_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    route_db = get_route(route_id, db, current_user)
    if route_db.status not in (RouteStatus.planned, RouteStatus.active):
        raise HTTPException(detail=f'Маршрут уже {route_db.status.value}', status_code=400)

    route_db.status = RouteStatus.cancelled
    db.commit()
    db.refresh(route_db)
    return route_db


@route_router.delete('/{route_id}/', response_model=dict)
async def delete_route(route_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    route_db = get_route(route_id, db, current_user)
    if route_db.status == RouteStatus.active:
        raise HTTPException(detail='Сначала отмените маршрут', status_code=400)

    db.delete(route_db)
    db.commit()
    return {'message': 'Маршрут удалён'}
