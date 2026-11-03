from fastapi import APIRouter, Depends, HTTPException
from database.models import (InventoryReservation, ReservationStatus, Inventory, WarehouseStatus, Delivery,
                             DeliveryStatus)
from database.schema import ReservationInputSchema, ReservationOutSchema
from api.dependencies import get_db, get_current_user
from clients.marketplace_services import get_order
from config import RESERVATION_LIFETIME
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

reservation_router = APIRouter(prefix='/reservations', tags=['Reservations'])


def finish_reservation(reservation_db: InventoryReservation, status: ReservationStatus):
    inventory_db = reservation_db.reservation_inventory
    inventory_db.reserved_quantity -= reservation_db.quantity
    if status == ReservationStatus.committed:
        inventory_db.quantity -= reservation_db.quantity
    reservation_db.status = status


def expire_reservations(db: Session):
    in_delivery = select(Delivery.order_id).where(Delivery.status != DeliveryStatus.cancelled)
    expired = db.query(InventoryReservation).filter(InventoryReservation.status == ReservationStatus.active,
                                                    InventoryReservation.expires_at < datetime.now(timezone.utc),
                                                    InventoryReservation.order_id.notin_(in_delivery)).all()
    for reservation_db in expired:
        finish_reservation(reservation_db, ReservationStatus.expired)
    if expired:
        db.commit()


def get_reservation(reservation_id: int, db: Session, current_user: dict):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    expire_reservations(db)
    reservation_db = db.query(InventoryReservation).filter(InventoryReservation.id == reservation_id).first()
    if not reservation_db:
        raise HTTPException(detail='Запись не найдена', status_code=400)
    return reservation_db


@reservation_router.post('/', response_model=ReservationOutSchema)
async def create_reservation(reservation: ReservationInputSchema, db: Session = Depends(get_db),
                             current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    inventory_db = db.query(Inventory).filter(Inventory.id == reservation.inventory_id).first()
    if not inventory_db:
        raise HTTPException(detail='Остаток не найден', status_code=400)

    if inventory_db.inventory_warehouse.status != WarehouseStatus.active:
        raise HTTPException(detail='Склад не работает', status_code=400)

    order = await get_order(reservation.order_id, current_user['token'])
    if order['product_id'] != inventory_db.product_id:
        raise HTTPException(detail='На этом остатке другой товар', status_code=400)

    if db.query(InventoryReservation).filter(
            InventoryReservation.order_id == reservation.order_id,
            InventoryReservation.status.in_([ReservationStatus.active, ReservationStatus.committed])).first():
        raise HTTPException(detail='Заказ уже зарезервирован', status_code=400)

    expire_reservations(db)
    available = inventory_db.quantity - inventory_db.reserved_quantity
    if order['quantity'] > available:
        raise HTTPException(detail=f'На складе доступно только {available}', status_code=400)

    reservation_db = InventoryReservation(**reservation.model_dump(), quantity=order['quantity'],
                                          expires_at=datetime.now(timezone.utc) + timedelta(
                                              minutes=RESERVATION_LIFETIME))
    inventory_db.reserved_quantity += order['quantity']
    db.add(reservation_db)
    db.commit()
    db.refresh(reservation_db)
    return reservation_db


@reservation_router.get('/', response_model=List[ReservationOutSchema])
async def list_reservation(order_id: Optional[int] = None, status: Optional[ReservationStatus] = None,
                           db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user['status'] != 'manager':
        raise HTTPException(detail='Недостаточно прав', status_code=403)

    expire_reservations(db)
    query = db.query(InventoryReservation)
    if order_id is not None:
        query = query.filter(InventoryReservation.order_id == order_id)
    if status is not None:
        query = query.filter(InventoryReservation.status == status)
    return query.all()


@reservation_router.get('/{reservation_id}/', response_model=ReservationOutSchema)
async def detail_reservation(reservation_id: int, db: Session = Depends(get_db),
                             current_user: dict = Depends(get_current_user)):
    return get_reservation(reservation_id, db, current_user)


@reservation_router.post('/{reservation_id}/commit/', response_model=ReservationOutSchema)
async def commit_reservation(reservation_id: int, db: Session = Depends(get_db),
                             current_user: dict = Depends(get_current_user)):
    reservation_db = get_reservation(reservation_id, db, current_user)
    if reservation_db.status != ReservationStatus.active:
        raise HTTPException(detail=f'Резерв уже {reservation_db.status.value}', status_code=400)

    finish_reservation(reservation_db, ReservationStatus.committed)
    db.commit()
    db.refresh(reservation_db)
    return reservation_db


@reservation_router.post('/{reservation_id}/release/', response_model=ReservationOutSchema)
async def release_reservation(reservation_id: int, db: Session = Depends(get_db),
                              current_user: dict = Depends(get_current_user)):
    reservation_db = get_reservation(reservation_id, db, current_user)
    if reservation_db.status != ReservationStatus.active:
        raise HTTPException(detail=f'Резерв уже {reservation_db.status.value}', status_code=400)

    finish_reservation(reservation_db, ReservationStatus.released)
    db.commit()
    db.refresh(reservation_db)
    return reservation_db
