from fastapi import APIRouter, Depends, HTTPException
from database.models import Courier, CourierStatus, Warehouse, Delivery, DeliveryStatus
from database.schema import CourierInputSchema, CourierStatusSchema, CourierOutSchema
from api.dependencies import get_db, get_current_user
from typing import List, Optional
from sqlalchemy.orm import Session

courier_router = APIRouter(prefix='/couriers', tags=['Couriers'])


def active_deliveries(db: Session, courier_id: int):
    return db.query(Delivery).filter(Delivery.courier_id == courier_id,
                                     Delivery.status.in_([DeliveryStatus.assigned, DeliveryStatus.in_transit])).count()


def update_courier_load(courier_db: Courier, db: Session):
    if courier_db.status not in (CourierStatus.available, CourierStatus.busy):
        return

    if active_deliveries(db, courier_db.id) >= courier_db.max_active_orders:
        courier_db.status = CourierStatus.busy
    else:
        courier_db.status = CourierStatus.available


def get_my_courier(db: Session, current_user: dict):
    courier_db = db.query(Courier).filter(Courier.user_id == current_user['id']).first()
    if not courier_db:
        raise HTTPException(detail='Вы не курьер', status_code=403)
    return courier_db


def check_courier(courier: CourierInputSchema, db: Session):
    if not db.query(Warehouse).filter(Warehouse.id == courier.warehouse_id).first():
        raise HTTPException(detail='Склад не найден', status_code=400)


@courier_router.post('/', response_model=CourierOutSchema)
async def create_courier(courier: CourierInputSchema, db: Session = Depends(get_db),
                         current_user: dict = Depends(get_current_user)):
    if db.query(Courier).filter(Courier.user_id == current_user['id']).first():
        raise HTTPException(detail='Вы уже курьер', status_code=400)

    check_courier(courier, db)
    courier_db = Courier(user_id=current_user['id'], **courier.model_dump())
    db.add(courier_db)
    db.commit()
    db.refresh(courier_db)
    return courier_db


@courier_router.get('/', response_model=List[CourierOutSchema])
async def list_courier(warehouse_id: Optional[int] = None, status: Optional[CourierStatus] = None,
                       db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    query = db.query(Courier)
    if warehouse_id is not None:
        query = query.filter(Courier.warehouse_id == warehouse_id)
    if status is not None:
        query = query.filter(Courier.status == status)
    return query.all()


@courier_router.get('/me/', response_model=CourierOutSchema)
async def my_courier(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_my_courier(db, current_user)


@courier_router.put('/me/status/', response_model=CourierOutSchema)
async def my_courier_status(courier_status: CourierStatusSchema, db: Session = Depends(get_db),
                            current_user: dict = Depends(get_current_user)):
    courier_db = get_my_courier(db, current_user)
    if courier_db.status == CourierStatus.suspended:
        raise HTTPException(detail='Вы отстранены, статус меняет менеджер', status_code=403)

    if courier_status.status not in (CourierStatus.offline, CourierStatus.available):
        raise HTTPException(detail='Можно поставить только offline или available', status_code=400)

    if courier_status.status == CourierStatus.offline and active_deliveries(db, courier_db.id):
        raise HTTPException(detail='Сначала завершите активные доставки', status_code=400)

    courier_db.status = courier_status.status
    update_courier_load(courier_db, db)
    db.commit()
    db.refresh(courier_db)
    return courier_db


@courier_router.get('/{courier_id}/', response_model=CourierOutSchema)
async def detail_courier(courier_id: int, db: Session = Depends(get_db),
                         current_user: dict = Depends(get_current_user)):
    courier_db = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    if current_user['status'] != 'manager' and courier_db.user_id != current_user['id']:
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    return courier_db


@courier_router.put('/{courier_id}/', response_model=dict)
async def update_courier(courier_id: int, courier: CourierInputSchema, db: Session = Depends(get_db),
                         current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    courier_db = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    check_courier(courier, db)
    if courier.warehouse_id != courier_db.warehouse_id and active_deliveries(db, courier_id):
        raise HTTPException(detail='У курьера есть активные доставки', status_code=400)

    for courier_key, courier_value in courier.model_dump().items():
        setattr(courier_db, courier_key, courier_value)

    update_courier_load(courier_db, db)
    db.commit()
    db.refresh(courier_db)
    return {'message': 'Курьер изменён'}


@courier_router.delete('/{courier_id}/', response_model=dict)
async def delete_courier(courier_id: int, db: Session = Depends(get_db),
                         current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    courier_db = db.query(Courier).filter(Courier.id == courier_id).first()
    if not courier_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    if active_deliveries(db, courier_id):
        raise HTTPException(detail='У курьера есть активные доставки', status_code=400)

    db.delete(courier_db)
    db.commit()
    return {'message': 'Курьер удалён'}
