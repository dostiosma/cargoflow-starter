"""Datos de prueba deterministas para los escenarios de concurrencia.

Los created_at son explicitos y crecientes: la seleccion FIFO de /assign
(ORDER BY created_at) es entonces totalmente determinista (V1 antes que V2, etc.).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.models import (
    Driver,
    DriverStatus,
    Order,
    OrderPriority,
    OrderStatus,
    Shipment,
    User,
    UserRole,
    Vehicle,
    VehicleStatus,
    VehicleType,
)

_BASE = datetime(2026, 1, 1, 8, 0, 0)  # naive (UTC), como las columnas DateTime del modelo


@dataclass(frozen=True)
class Seeded:
    token: str
    shipment_ids: tuple
    order_ids: tuple
    vehicle_ids: tuple
    driver_ids: tuple
    names: dict  # str(uuid) -> "S1" / "V2" / "D1" / "O1" para mensajes legibles


def seed_scenario(engine, *, shipments: int, vehicles: int, drivers: int) -> Seeded:
    names: dict = {}
    admin_id = uuid.uuid4()
    vehicle_ids, driver_ids, order_ids, shipment_ids = [], [], [], []

    with Session(engine) as session:
        session.add(User(id=admin_id, email="admin@example.com", password_hash="x", role=UserRole.admin))

        for i in range(vehicles):
            vid = uuid.uuid4()
            vehicle_ids.append(vid)
            names[str(vid)] = f"V{i + 1}"
            session.add(
                Vehicle(
                    id=vid,
                    plate=f"TST-{i + 1:03d}",
                    type=VehicleType.van,
                    capacity_kg=1000,
                    status=VehicleStatus.available,
                    created_at=_BASE + timedelta(seconds=i),
                )
            )

        for i in range(drivers):
            uid, did = uuid.uuid4(), uuid.uuid4()
            driver_ids.append(did)
            names[str(did)] = f"D{i + 1}"
            session.add(
                User(id=uid, email=f"driver{i + 1}@example.com", password_hash="x", role=UserRole.driver)
            )
            session.add(
                Driver(
                    id=did,
                    user_id=uid,
                    name=f"Conductor {i + 1}",
                    status=DriverStatus.available,
                    created_at=_BASE + timedelta(seconds=i),
                )
            )

        for i in range(shipments):
            oid, sid = uuid.uuid4(), uuid.uuid4()
            order_ids.append(oid)
            shipment_ids.append(sid)
            names[str(oid)] = f"O{i + 1}"
            names[str(sid)] = f"S{i + 1}"
            session.add(
                Order(
                    id=oid,
                    customer_name=f"Cliente {i + 1}",
                    origin_address="A",
                    destination_address="B",
                    priority=OrderPriority.normal,
                    status=OrderStatus.pending,
                    created_at=_BASE + timedelta(seconds=i),
                )
            )
            session.add(Shipment(id=sid, order_id=oid, status=OrderStatus.pending))

        session.commit()

    token, _ = create_access_token(subject=str(admin_id))
    return Seeded(
        token=token,
        shipment_ids=tuple(shipment_ids),
        order_ids=tuple(order_ids),
        vehicle_ids=tuple(vehicle_ids),
        driver_ids=tuple(driver_ids),
        names=names,
    )
