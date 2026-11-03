from database.db import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, ForeignKey, DateTime, Enum, Text, UniqueConstraint
from typing import List, Optional
from enum import Enum as PyEnum
from datetime import datetime
from sqlalchemy import func


class WarehouseStatus(PyEnum):
    active = 'active'
    inactive = 'inactive'
    maintenance = 'maintenance'


class ReservationStatus(PyEnum):
    active = 'active'
    committed = 'committed'
    released = 'released'
    expired = 'expired'


class TransportType(PyEnum):
    walking = 'walking'
    bicycle = 'bicycle'
    motorcycle = 'motorcycle'
    car = 'car'


class CourierStatus(PyEnum):
    offline = 'offline'
    available = 'available'
    busy = 'busy'
    suspended = 'suspended'


class DeliveryStatus(PyEnum):
    pending = 'pending'
    assigned = 'assigned'
    in_transit = 'in_transit'
    delivered = 'delivered'
    failed = 'failed'
    cancelled = 'cancelled'


class RouteStatus(PyEnum):
    planned = 'planned'
    active = 'active'
    completed = 'completed'
    cancelled = 'cancelled'


class StopType(PyEnum):
    pickup = 'pickup'
    dropoff = 'dropoff'


class StopStatus(PyEnum):
    pending = 'pending'
    arrived = 'arrived'
    completed = 'completed'
    skipped = 'skipped'


class Warehouse(Base):
    __tablename__ = 'warehouse'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    street: Mapped[str] = mapped_column(String)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    capacity: Mapped[int] = mapped_column(Integer)
    status: Mapped[WarehouseStatus] = mapped_column(Enum(WarehouseStatus), default=WarehouseStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    warehouse_inventory: Mapped[List['Inventory']] = relationship('Inventory', back_populates='inventory_warehouse',
                                                                  cascade='all, delete-orphan')
    warehouse_courier: Mapped[List['Courier']] = relationship('Courier', back_populates='courier_warehouse',
                                                              cascade='all, delete-orphan')
    warehouse_delivery: Mapped[List['Delivery']] = relationship('Delivery', back_populates='delivery_warehouse',
                                                                cascade='all, delete-orphan')


class Inventory(Base):
    __tablename__ = 'inventory'
    __table_args__ = (UniqueConstraint('warehouse_id', 'product_id'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey('warehouse.id', ondelete='CASCADE'))
    product_id: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())

    inventory_warehouse: Mapped[Warehouse] = relationship(Warehouse, back_populates='warehouse_inventory')
    inventory_reservation: Mapped[List['InventoryReservation']] = relationship(
        'InventoryReservation', back_populates='reservation_inventory', cascade='all, delete-orphan')


class InventoryReservation(Base):
    __tablename__ = 'inventory_reservation'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer)
    inventory_id: Mapped[int] = mapped_column(ForeignKey('inventory.id', ondelete='CASCADE'))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[ReservationStatus] = mapped_column(Enum(ReservationStatus), default=ReservationStatus.active)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reservation_inventory: Mapped[Inventory] = relationship(Inventory, back_populates='inventory_reservation')


class Courier(Base):
    __tablename__ = 'courier'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey('warehouse.id', ondelete='CASCADE'))
    transport_type: Mapped[TransportType] = mapped_column(Enum(TransportType))
    status: Mapped[CourierStatus] = mapped_column(Enum(CourierStatus), default=CourierStatus.offline)
    max_active_orders: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    courier_warehouse: Mapped[Warehouse] = relationship(Warehouse, back_populates='warehouse_courier')
    courier_location: Mapped[List['CourierLocation']] = relationship('CourierLocation',
                                                                     back_populates='location_courier',
                                                                     cascade='all, delete-orphan')
    courier_delivery: Mapped[List['Delivery']] = relationship('Delivery', back_populates='delivery_courier')
    courier_route: Mapped[List['Route']] = relationship('Route', back_populates='route_courier',
                                                        cascade='all, delete-orphan')


class CourierLocation(Base):
    __tablename__ = 'courier_location'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    courier_id: Mapped[int] = mapped_column(ForeignKey('courier.id', ondelete='CASCADE'))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    location_courier: Mapped[Courier] = relationship(Courier, back_populates='courier_location')


class Delivery(Base):
    __tablename__ = 'delivery'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey('warehouse.id', ondelete='CASCADE'))
    courier_id: Mapped[Optional[int]] = mapped_column(ForeignKey('courier.id', ondelete='SET NULL'), nullable=True)
    tracking_code: Mapped[str] = mapped_column(String, unique=True)
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus), default=DeliveryStatus.pending)
    destination_address: Mapped[str] = mapped_column(String)
    destination_latitude: Mapped[float] = mapped_column(Float)
    destination_longitude: Mapped[float] = mapped_column(Float)
    estimated_delivery_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    delivery_warehouse: Mapped[Warehouse] = relationship(Warehouse, back_populates='warehouse_delivery')
    delivery_courier: Mapped[Optional[Courier]] = relationship(Courier, back_populates='courier_delivery')
    delivery_stop: Mapped[List['RouteStop']] = relationship('RouteStop', back_populates='stop_delivery',
                                                            cascade='all, delete-orphan')
    delivery_event: Mapped[List['TrackingEvent']] = relationship('TrackingEvent', back_populates='event_delivery',
                                                                 cascade='all, delete-orphan',
                                                                 order_by='TrackingEvent.id')


class Route(Base):
    __tablename__ = 'route'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    courier_id: Mapped[int] = mapped_column(ForeignKey('courier.id', ondelete='CASCADE'))
    status: Mapped[RouteStatus] = mapped_column(Enum(RouteStatus), default=RouteStatus.planned)
    total_distance_km: Mapped[float] = mapped_column(Float)
    estimated_duration_min: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    route_courier: Mapped[Courier] = relationship(Courier, back_populates='courier_route')
    route_stop: Mapped[List['RouteStop']] = relationship('RouteStop', back_populates='stop_route',
                                                         cascade='all, delete-orphan', order_by='RouteStop.sequence')


class RouteStop(Base):
    __tablename__ = 'route_stop'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(ForeignKey('route.id', ondelete='CASCADE'))
    delivery_id: Mapped[int] = mapped_column(ForeignKey('delivery.id', ondelete='CASCADE'))
    stop_type: Mapped[StopType] = mapped_column(Enum(StopType))
    sequence: Mapped[int] = mapped_column(Integer)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    status: Mapped[StopStatus] = mapped_column(Enum(StopStatus), default=StopStatus.pending)
    arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    stop_route: Mapped[Route] = relationship(Route, back_populates='route_stop')
    stop_delivery: Mapped[Delivery] = relationship(Delivery, back_populates='delivery_stop')


class TrackingEvent(Base):
    __tablename__ = 'tracking_event'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey('delivery.id', ondelete='CASCADE'))
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus))
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event_delivery: Mapped[Delivery] = relationship(Delivery, back_populates='delivery_event')
