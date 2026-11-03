from fastapi import APIRouter, Depends, HTTPException
from database.models import Warehouse, Inventory, Delivery, DeliveryStatus, WarehouseStatus
from database.schema import WarehouseInputSchema, WarehouseOutSchema
from api.dependencies import get_db, get_current_user
from clients.marketplace_services import get_city
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

warehouse_router = APIRouter(prefix='/warehouses', tags=['Warehouses'])


def stored_quantity(db: Session, warehouse_id: int):
    return db.query(func.coalesce(func.sum(Inventory.quantity), 0)).filter(
        Inventory.warehouse_id == warehouse_id).scalar()


async def check_warehouse(warehouse: WarehouseInputSchema, db: Session, token: str,
                          warehouse_id: Optional[int] = None):
    await get_city(warehouse.city_id, token)

    if db.query(Warehouse).filter(Warehouse.code == warehouse.code, Warehouse.id != warehouse_id).first():
        raise HTTPException(detail='Склад с таким кодом уже есть', status_code=400)


@warehouse_router.post('/', response_model=WarehouseOutSchema)
async def create_warehouse(warehouse: WarehouseInputSchema, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    await check_warehouse(warehouse, db, current_user['token'])
    warehouse_db = Warehouse(**warehouse.model_dump())
    db.add(warehouse_db)
    db.commit()
    db.refresh(warehouse_db)
    return warehouse_db


@warehouse_router.get('/', response_model=List[WarehouseOutSchema])
async def list_warehouse(city_id: Optional[int] = None, status: Optional[WarehouseStatus] = None,
                         db: Session = Depends(get_db)):
    query = db.query(Warehouse)
    if city_id is not None:
        query = query.filter(Warehouse.city_id == city_id)
    if status is not None:
        query = query.filter(Warehouse.status == status)
    return query.all()


@warehouse_router.get('/{warehouse_id}/', response_model=WarehouseOutSchema)
async def detail_warehouse(warehouse_id: int, db: Session = Depends(get_db)):
    warehouse_db = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    return warehouse_db


@warehouse_router.put('/{warehouse_id}/', response_model=dict)
async def update_warehouse(warehouse_id: int, warehouse: WarehouseInputSchema, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    warehouse_db = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    await check_warehouse(warehouse, db, current_user['token'], warehouse_id)
    if stored_quantity(db, warehouse_id) > warehouse.capacity:
        raise HTTPException(detail='Товара на складе больше новой вместимости', status_code=400)

    for warehouse_key, warehouse_value in warehouse.model_dump().items():
        setattr(warehouse_db, warehouse_key, warehouse_value)

    db.commit()
    db.refresh(warehouse_db)
    return {'message': 'Склад изменён'}


@warehouse_router.delete('/{warehouse_id}/', response_model=dict)
async def delete_warehouse(warehouse_id: int, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    warehouse_db = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    if db.query(Delivery).filter(Delivery.warehouse_id == warehouse_id,
                                 Delivery.status.notin_([DeliveryStatus.delivered, DeliveryStatus.cancelled])).first():
        raise HTTPException(detail='У склада есть незавершённые доставки', status_code=400)

    if db.query(Inventory).filter(Inventory.warehouse_id == warehouse_id, Inventory.reserved_quantity > 0).first():
        raise HTTPException(detail='На складе есть зарезервированный товар', status_code=400)

    db.delete(warehouse_db)
    db.commit()
    return {'message': 'Склад удалён'}
