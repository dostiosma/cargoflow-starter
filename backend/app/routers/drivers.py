import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user
from app.models import Driver, OrderStatus, Shipment, User, UserRole
from app.operating_day import operating_day_bounds_utc
from app.schemas import DriverOut, DriverRouteShipmentOut

router = APIRouter(prefix="/api/drivers", tags=["drivers"])


@router.get("", response_model=list[DriverOut])
def list_drivers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Driver).order_by(Driver.name).all()


@router.get("/{driver_id}/shipments", response_model=list[DriverRouteShipmentOut])
def driver_route(
    driver_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Spec seccion 7, "ruta del conductor". `driver_id` es el Driver.id, no el User.id.
    #
    # Autorizacion: la propiedad se comprueba ANTES de consultar si el Driver existe,
    # para que un `driver` que pida un id ajeno reciba 403 exista o no ese Driver
    # (el 404 solo lo ve un `admin`). Un `driver` sin Driver asociado no puede
    # consultar ninguna ruta: su id propio es None, que nunca coincide.
    if current_user.role == UserRole.driver:
        own_driver_id = db.query(Driver.id).filter(Driver.user_id == current_user.id).scalar()
        if own_driver_id != driver_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para consultar la ruta de este conductor",
            )

    if db.query(Driver.id).filter(Driver.id == driver_id).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conductor no encontrado")

    # Ruta = activos (assigned / in_transit, de cualquier dia) + terminales
    # (delivered / cancelled) cuya actual_delivery cae en el dia operativo en curso:
    # inicio inclusive, fin exclusive. No se filtra por estado dentro de cada grupo.
    day_start, day_end = operating_day_bounds_utc()

    return (
        db.query(Shipment)
        .options(joinedload(Shipment.order))
        .filter(Shipment.driver_id == driver_id)
        .filter(
            or_(
                Shipment.status.in_([OrderStatus.assigned, OrderStatus.in_transit]),
                and_(
                    Shipment.status.in_([OrderStatus.delivered, OrderStatus.cancelled]),
                    Shipment.actual_delivery >= day_start,
                    Shipment.actual_delivery < day_end,
                ),
            )
        )
        .order_by(Shipment.assigned_at.asc(), Shipment.id.asc())
        .all()
    )
