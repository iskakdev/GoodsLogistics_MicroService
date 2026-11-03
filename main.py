from fastapi import FastAPI
from api import warehouse, inventory, reservation, courier, courier_location, delivery, tracking, route, route_stop
from database.db import Base, engine
import uvicorn

Base.metadata.create_all(bind=engine)

logistics_app = FastAPI(title='Logistics Service')
logistics_app.include_router(warehouse.warehouse_router)
logistics_app.include_router(inventory.inventory_router)
logistics_app.include_router(reservation.reservation_router)
logistics_app.include_router(courier.courier_router)
logistics_app.include_router(courier_location.courier_location_router)
logistics_app.include_router(delivery.delivery_router)
logistics_app.include_router(tracking.tracking_router)
logistics_app.include_router(route.route_router)
logistics_app.include_router(route_stop.route_stop_router)

if __name__ == '__main__':
    uvicorn.run(logistics_app, host='127.0.0.1', port=8005)
