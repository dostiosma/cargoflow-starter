import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.events import publish_shipment_status_changed
from app.models import Order, Shipment, User
from app.schemas import ShipmentOut, ShipmentStatusUpdate

router = APIRouter(prefix="/api/shipments", tags=["shipments"])


@router.get("", response_model=list[ShipmentOut])
def list_shipments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Shipment).order_by(Shipment.order_id).all()


@router.get("/{shipment_id}", response_model=ShipmentOut)
def get_shipment(
    shipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio no encontrado")
    return shipment


@router.patch("/{shipment_id}/status", response_model=ShipmentOut)
def update_shipment_status(
    shipment_id: uuid.UUID,
    payload: ShipmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio no encontrado")
    shipment.status = payload.status
    db.commit()
    db.refresh(shipment)
    publish_shipment_status_changed(shipment.id, shipment.status)
    return shipment


from datetime import datetime, timedelta, timezone

from app.models import Driver, Vehicle, VehicleStatus, DriverStatus, OrderStatus
from app.schemas import ShipmentAssignResponse


@router.post("/{shipment_id}/assign", response_model=ShipmentAssignResponse)
def assign_shipment(
    shipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1) Bloquear la propia fila del Shipment antes de leer/decidir nada. Esto
    # evita que dos requests concurrentes sobre el MISMO shipment_id pasen
    # ambas la comprobacion de idempotencia antes de que ninguna comitee: la
    # segunda queda esperando aca hasta que la primera termine, y al
    # destrabarse relee el estado ya actualizado por la primera.
    shipment = (
        db.query(Shipment)
        .filter(Shipment.id == shipment_id)
        .with_for_update()
        .first()
    )
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio no encontrado")

    # 2) Idempotencia (D3), ya con el shipment bloqueado y con su estado mas
    # reciente: si ya tiene vehiculo/conductor o no esta pending, devolver la
    # asignacion existente tal cual, sin volver a buscar recursos, sin commit
    # adicional y sin publicar el evento de nuevo.
    if shipment.status != OrderStatus.pending or shipment.vehicle_id or shipment.driver_id:
        return {
            "id": shipment.id,
            "order_id": shipment.order_id,
            "vehicle_id": shipment.vehicle_id,
            "driver_id": shipment.driver_id,
            "status": shipment.status,
            "message": "El envio ya estaba asignado",
        }

    # 3-4) Seleccion FIFO del vehiculo disponible, protegida contra una
    # carrera entre shipments DISTINTOS con FOR UPDATE SKIP LOCKED bajo
    # Postgres: si otra transaccion ya tiene lock sobre el vehiculo mas
    # antiguo disponible, esta salta esa fila y toma la siguiente en vez de
    # esperar o arriesgarse a leer un estado que dejo de ser valido.
    vehicle_query = (
        db.query(Vehicle)
        .filter(Vehicle.status == VehicleStatus.available)
        .order_by(Vehicle.created_at)
    )
    if db.bind.dialect.name == "postgresql":
        vehicle_query = vehicle_query.with_for_update(skip_locked=True)
    vehicle = vehicle_query.first()
    if vehicle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay vehiculos disponibles")

    # 5-6) Mismo patron para el conductor disponible.
    driver_query = (
        db.query(Driver)
        .filter(Driver.status == DriverStatus.available)
        .order_by(Driver.created_at)
    )
    if db.bind.dialect.name == "postgresql":
        driver_query = driver_query.with_for_update(skip_locked=True)
    driver = driver_query.first()
    if driver is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay conductores disponibles")

    # 7-12) Asignacion real: recursos, estado del shipment, ETA y espejo en
    # Order, todo dentro de la misma transaccion (un unico commit en el
    # punto 13).
    now = datetime.now(timezone.utc)
    shipment.vehicle_id = vehicle.id
    shipment.driver_id = driver.id
    shipment.status = OrderStatus.assigned
    shipment.assigned_at = now
    shipment.estimated_delivery = now + timedelta(hours=4)
    vehicle.status = VehicleStatus.in_use
    driver.status = DriverStatus.busy

    order = shipment.order
    order.status = OrderStatus.assigned

    # 13) Un unico commit para toda la asignacion.
    db.commit()
    db.refresh(shipment)

    # 14) Publicar el evento solo despues de un commit exitoso, y solo en
    # este camino real de asignacion (nunca en el camino idempotente).
    publish_shipment_status_changed(shipment.id, shipment.status)

    return {
        "id": shipment.id,
        "order_id": shipment.order_id,
        "vehicle_id": shipment.vehicle_id,
        "driver_id": shipment.driver_id,
        "status": shipment.status,
        "message": f"Asignado vehiculo {vehicle.plate} (conductor: {driver.name})"
    }
