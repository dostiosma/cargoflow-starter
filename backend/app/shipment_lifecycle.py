"""Efectos de un Shipment que llega a un estado terminal.

Seccion 6 del master spec ("Maquina de estados operacional"): al llegar a un
estado terminal se liberan Vehicle y Driver, se fija `actual_delivery` y
`delay_risk_score` vuelve a `null`.

Este modulo solo modifica objetos de la sesion recibida: NO hace commit y NO
publica eventos. Quien lo invoca controla la transaccion (un unico commit) y
publica el evento despues de ese commit.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Driver, DriverStatus, OrderStatus, Shipment, Vehicle, VehicleStatus


def apply_terminal_state(shipment: Shipment, new_status: OrderStatus, db: Session) -> None:
    shipment.status = new_status
    shipment.actual_delivery = datetime.now(timezone.utc)
    shipment.delay_risk_score = None

    # Se liberan exclusivamente el Vehicle y el Driver referenciados por este
    # shipment (vehicle_id / driver_id); nunca se buscan recursos de forma
    # generica.
    if shipment.vehicle_id is not None:
        vehicle = db.query(Vehicle).filter(Vehicle.id == shipment.vehicle_id).first()
        if vehicle is not None:
            vehicle.status = VehicleStatus.available

    if shipment.driver_id is not None:
        driver = db.query(Driver).filter(Driver.id == shipment.driver_id).first()
        if driver is not None:
            driver.status = DriverStatus.available
