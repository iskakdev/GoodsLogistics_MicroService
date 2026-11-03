from pydantic import BaseModel, Field
from database.models import (WarehouseStatus, ReservationStatus, TransportType, CourierStatus, DeliveryStatus,
                             RouteStatus, StopType, StopStatus)
from datetime import datetime
from typing import List, Optional


class WarehouseInputSchema(BaseModel):
    city_id: int
    code: str
    name: str
    street: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    capacity: int = Field(gt=0)
    status: WarehouseStatus = WarehouseStatus.active


class WarehouseOutSchema(BaseModel):
    id: int
    city_id: int
    code: str
    name: str
    street: str
    latitude: float
    longitude: float
    capacity: int
    status: WarehouseStatus
    created_at: datetime


class InventoryInputSchema(BaseModel):
    warehouse_id: int
    product_id: int
    quantity: int = Field(ge=0)


class InventoryUpdateSchema(BaseModel):
    quantity: int = Field(ge=0)


class InventoryOutSchema(BaseModel):
    id: int
    warehouse_id: int
    product_id: int
    quantity: int
    reserved_quantity: int
    updated_at: datetime


class ReservationInputSchema(BaseModel):
    order_id: int
    inventory_id: int


class ReservationOutSchema(BaseModel):
    id: int
    order_id: int
    inventory_id: int
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    created_at: datetime


class CourierInputSchema(BaseModel):
    warehouse_id: int
    transport_type: TransportType
    status: CourierStatus = CourierStatus.offline
    max_active_orders: int = Field(default=1, ge=1)


class CourierStatusSchema(BaseModel):
    status: CourierStatus


class CourierOutSchema(BaseModel):
    id: int
    user_id: int
    warehouse_id: int
    transport_type: TransportType
    status: CourierStatus
    max_active_orders: int
    created_at: datetime


class CourierLocationInputSchema(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CourierLocationOutSchema(BaseModel):
    id: int
    courier_id: int
    latitude: float
    longitude: float
    recorded_at: datetime


class DeliveryInputSchema(BaseModel):
    order_id: int
    warehouse_id: int
    destination_address: str
    destination_latitude: float = Field(ge=-90, le=90)
    destination_longitude: float = Field(ge=-180, le=180)
    estimated_delivery_at: Optional[datetime] = None


class DeliveryAssignSchema(BaseModel):
    courier_id: int


class DeliveryStatusSchema(BaseModel):
    status: DeliveryStatus
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    description: Optional[str] = None


class DeliveryOutSchema(BaseModel):
    id: int
    order_id: int
    warehouse_id: int
    courier_id: Optional[int]
    tracking_code: str
    status: DeliveryStatus
    destination_address: str
    destination_latitude: float
    destination_longitude: float
    estimated_delivery_at: Optional[datetime]
    delivered_at: Optional[datetime]
    created_at: datetime


class TrackingEventOutSchema(BaseModel):
    id: int
    status: DeliveryStatus
    latitude: Optional[float]
    longitude: Optional[float]
    description: str
    created_at: datetime


class TrackingOutSchema(BaseModel):
    tracking_code: str
    status: DeliveryStatus
    destination_address: str
    estimated_delivery_at: Optional[datetime]
    delivered_at: Optional[datetime]
    delivery_event: List[TrackingEventOutSchema]


class RouteInputSchema(BaseModel):
    courier_id: int
    delivery_ids: List[int] = Field(min_length=1)


class RouteStopStatusSchema(BaseModel):
    status: StopStatus


class RouteStopOutSchema(BaseModel):
    id: int
    route_id: int
    delivery_id: int
    stop_type: StopType
    sequence: int
    latitude: float
    longitude: float
    status: StopStatus
    arrived_at: Optional[datetime]


class RouteOutSchema(BaseModel):
    id: int
    courier_id: int
    status: RouteStatus
    total_distance_km: float
    estimated_duration_min: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    route_stop: List[RouteStopOutSchema]
