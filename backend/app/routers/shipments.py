import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.events import publish_shipment_risk_alert, publish_shipment_status_changed
from app.models import Order, OrderStatus, Shipment, User
from app.schemas import ShipmentOut, ShipmentRiskUpdate, ShipmentStatusUpdate
from app.shipment_lifecycle import apply_terminal_state

router = APIRouter(prefix="/api/shipments", tags=["shipments"])


@router.get("", response_model=list[ShipmentOut])
def list_shipments(
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista los envios; `?status=` filtra por Shipment.status (secciones 7 y 9 del master spec).

    Acepta un unico valor del enum de estados. Sin filtro devuelve todos, y sin
    coincidencias devuelve []. Un valor invalido (mayusculas o vacio incluidos) lo
    rechaza FastAPI con 422. El parametro interno se llama status_filter para no
    tapar el modulo `status` importado de FastAPI.
    """
    query = db.query(Shipment)
    if status_filter is not None:
        # Shipment es la fuente de verdad del estado operacional (seccion 6)
        query = query.filter(Shipment.status == status_filter)
    return query.order_by(Shipment.order_id).all()


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


# Unicas transiciones que este endpoint permite (seccion 6 del master spec):
#   assigned -> in_transit -> delivered
# Cualquier otra combinacion se rechaza con 400, incluido `cancelled`: la
# cancelacion no se hace por este endpoint.
VALID_SHIPMENT_TRANSITIONS = {
    OrderStatus.assigned: OrderStatus.in_transit,
    OrderStatus.in_transit: OrderStatus.delivered,
}


@router.patch("/{shipment_id}/status", response_model=ShipmentOut)
def update_shipment_status(
    shipment_id: uuid.UUID,
    payload: ShipmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Decision de implementacion (no es un requisito textual del Spec):
    # bloquear la fila del Shipment antes de validar la transicion, con el
    # mismo patron que assign_shipment (Block 4). Asi, dos PATCH concurrentes
    # sobre el mismo shipment no validan ambos contra el mismo estado de
    # partida: el segundo espera, relee el estado ya actualizado y se valida
    # contra ese.
    shipment = (
        db.query(Shipment)
        .filter(Shipment.id == shipment_id)
        .with_for_update()
        .first()
    )
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio no encontrado")

    if VALID_SHIPMENT_TRANSITIONS.get(shipment.status) != payload.status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transicion invalida: {shipment.status.value} -> {payload.status.value}",
        )

    if payload.status == OrderStatus.delivered:
        # Estado terminal: libera exclusivamente el Vehicle/Driver referenciados
        # por este shipment, fija actual_delivery y resetea delay_risk_score.
        apply_terminal_state(shipment, OrderStatus.delivered, db)
    else:
        shipment.status = payload.status

    # Los cambios operacionales del Shipment se reflejan en Order.status.
    shipment.order.status = shipment.status

    db.commit()
    db.refresh(shipment)
    publish_shipment_status_changed(shipment.id, shipment.status)
    return shipment


# Umbral de alerta de riesgo (secciones 6, 8 y 9 del master spec): el evento
# risk_alert se publica solo cuando delay_risk_score es ESTRICTAMENTE mayor.
RISK_ALERT_THRESHOLD = 0.7


@router.patch("/{shipment_id}/risk", response_model=ShipmentOut)
def update_shipment_risk(
    shipment_id: uuid.UUID,
    payload: ShipmentRiskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persiste delay_risk_score calculado por n8n (secciones 6, 7 y 9 del master spec).

    Solo se actualiza con el Shipment en `in_transit`; en cualquier otro estado
    responde 400. El rango 0-1 (extremos incluidos) lo valida ShipmentRiskUpdate:
    un body invalido o un valor fuera de rango responde 422 antes de llegar aqui.
    """
    # Decision de implementacion (no es un requisito textual del Spec): bloquear
    # la fila del Shipment antes de validar el estado, con el mismo patron que
    # update_shipment_status y assign_shipment. Asi un PATCH concurrente a
    # delivered/cancelled no deja un score no nulo en un shipment que ya es
    # terminal (seccion 6: delay_risk_score vuelve a null).
    shipment = (
        db.query(Shipment)
        .filter(Shipment.id == shipment_id)
        .with_for_update()
        .first()
    )
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio no encontrado")

    if shipment.status != OrderStatus.in_transit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Solo se puede actualizar el riesgo de un envio en in_transit "
                f"(estado actual: {shipment.status.value})"
            ),
        )

    shipment.delay_risk_score = payload.delay_risk_score

    db.commit()
    db.refresh(shipment)

    # Primero commit, despues evento: nunca se publica un risk_alert sobre un
    # cambio que no quedo persistido (seccion 8). Un fallo de Redis lo absorbe
    # events.py y no afecta a esta respuesta.
    if shipment.delay_risk_score > RISK_ALERT_THRESHOLD:
        publish_shipment_risk_alert(shipment.id, shipment.delay_risk_score)
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
