import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
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
    return shipment


from app.models import Driver, Vehicle, VehicleStatus, DriverStatus, OrderStatus
from app.schemas import ShipmentAssignResponse


@router.post("/{shipment_id}/assign", response_model=ShipmentAssignResponse)
def assign_shipment(
    shipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio no encontrado")

    vehicle = db.query(Vehicle).filter(Vehicle.status == VehicleStatus.available).order_by(Vehicle.created_at).first()
    if vehicle is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay vehiculos disponibles")

    driver = db.query(Driver).filter(Driver.status == DriverStatus.available).order_by(Driver.created_at).first()
    if driver is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay conductores disponibles")

    shipment.vehicle_id = vehicle.id
    shipment.driver_id = driver.id
    shipment.status = OrderStatus.assigned
    db.commit()
    db.refresh(shipment)

    return {
        "id": shipment.id,
        "order_id": shipment.order_id,
        "vehicle_id": shipment.vehicle_id,
        "driver_id": shipment.driver_id,
        "status": shipment.status,
        "message": f"Asignado vehiculo {vehicle.plate} (conductor: {driver.name})"
    }
