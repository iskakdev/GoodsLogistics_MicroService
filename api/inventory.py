from fastapi import APIRouter, Depends, HTTPException
from database.models import Inventory, Warehouse
from database.schema import InventoryInputSchema, InventoryUpdateSchema, InventoryOutSchema
from api.dependencies import get_db, get_current_user
from api.warehouse import stored_quantity
from api.reservation import expire_reservations
from clients.marketplace_services import get_product
from typing import List, Optional
from sqlalchemy.orm import Session

inventory_router = APIRouter(prefix='/inventories', tags=['Inventories'])


@inventory_router.post('/', response_model=InventoryOutSchema)
async def create_inventory(inventory: InventoryInputSchema, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    warehouse_db = db.query(Warehouse).filter(Warehouse.id == inventory.warehouse_id).first()
    if not warehouse_db:
        raise HTTPException(detail='Склад не найден', status_code=400)

    await get_product(inventory.product_id, current_user['token'])
    if db.query(Inventory).filter(Inventory.warehouse_id == inventory.warehouse_id,
                                  Inventory.product_id == inventory.product_id).first():
        raise HTTPException(detail='Этот товар уже есть на складе', status_code=400)

    if stored_quantity(db, warehouse_db.id) + inventory.quantity > warehouse_db.capacity:
        raise HTTPException(detail='На складе не хватает места', status_code=400)

    inventory_db = Inventory(**inventory.model_dump())
    db.add(inventory_db)
    db.commit()
    db.refresh(inventory_db)
    return inventory_db


@inventory_router.get('/', response_model=List[InventoryOutSchema])
async def list_inventory(warehouse_id: Optional[int] = None, product_id: Optional[int] = None,
                         db: Session = Depends(get_db)):
    expire_reservations(db)
    query = db.query(Inventory)
    if warehouse_id is not None:
        query = query.filter(Inventory.warehouse_id == warehouse_id)
    if product_id is not None:
        query = query.filter(Inventory.product_id == product_id)
    return query.all()


@inventory_router.get('/{inventory_id}/', response_model=InventoryOutSchema)
async def detail_inventory(inventory_id: int, db: Session = Depends(get_db)):
    expire_reservations(db)
    inventory_db = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not inventory_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    return inventory_db


@inventory_router.put('/{inventory_id}/', response_model=dict)
async def update_inventory(inventory_id: int, inventory: InventoryUpdateSchema, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    expire_reservations(db)
    inventory_db = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not inventory_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    if inventory.quantity < inventory_db.reserved_quantity:
        raise HTTPException(detail=f'Зарезервировано {inventory_db.reserved_quantity}, меньше нельзя',
                            status_code=400)

    warehouse_db = inventory_db.inventory_warehouse
    if stored_quantity(db, warehouse_db.id) - inventory_db.quantity + inventory.quantity > warehouse_db.capacity:
        raise HTTPException(detail='На складе не хватает места', status_code=400)

    inventory_db.quantity = inventory.quantity
    db.commit()
    db.refresh(inventory_db)
    return {'message': 'Остаток изменён'}


@inventory_router.delete('/{inventory_id}/', response_model=dict)
async def delete_inventory(inventory_id: int, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    expire_reservations(db)
    inventory_db = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not inventory_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)

    if inventory_db.reserved_quantity > 0:
        raise HTTPException(detail='Товар зарезервирован, удалить нельзя', status_code=400)

    db.delete(inventory_db)
    db.commit()
    return {'message': 'Остаток удалён'}
