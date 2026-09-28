import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.events import publish_shipment_status_changed
from app.models import Order, OrderStatus, Shipment, User
from app.schemas import OrderCreate, OrderOut, OrderStatusUpdate
from app.shipment_lifecycle import apply_terminal_state

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = Order(
        customer_name=payload.customer_name,
        origin_address=payload.origin_address,
        destination_address=payload.destination_address,
        priority=payload.priority,
    )
    db.add(order)
    db.flush()  # asigna order.id sin cerrar la transaccion
    db.add(Shipment(order_id=order.id))  # status=pending por default del modelo
    db.commit()  # un solo commit: Order y Shipment en la misma transaccion (D1)
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderOut])
def list_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Order).order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
    return order


# Estados del Shipment desde los que se puede cancelar (seccion 6 del master
# spec): pending / assigned / in_transit -> cancelled. `delivered` y `cancelled`
# son terminales y no se cancelan.
CANCELLABLE_SHIPMENT_STATES = {
    OrderStatus.pending,
    OrderStatus.assigned,
    OrderStatus.in_transit,
}


@router.patch("/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: uuid.UUID,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancelacion administrativa (seccion 6 y 7 del master spec).

    Este endpoint solo acepta `{"status": "cancelled"}`: el progreso operacional
    (assigned -> in_transit -> delivered) lo controla el Shipment, no el Order.
    La cancelacion se propaga al Shipment y libera los recursos asignados dentro
    de la misma transaccion.
    """
    # Orden de locks: Shipment -> Order -> Vehicle/Driver. El Shipment se
    # bloquea primero (es la fuente de verdad y el mismo orden que usan
    # assign_shipment y update_shipment_status), asi que no se busca primero el
    # Order con lock: invertir el orden podria producir un deadlock.
    shipment = (
        db.query(Shipment)
        .filter(Shipment.order_id == order_id)
        .with_for_update()
        .first()
    )
    if shipment is None:
        order_exists = db.query(Order.id).filter(Order.id == order_id).first() is not None
        if not order_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
        # El spec garantiza 1 Order = 1 Shipment (D1/D2): un Order sin Shipment es
        # una inconsistencia de datos. No se modifica nada.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El pedido no tiene un envio asociado",
        )

    if payload.status != OrderStatus.cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este endpoint solo permite cancelar (status=cancelled)",
        )

    # El Shipment es la fuente de verdad para decidir si la cancelacion es valida.
    if shipment.status not in CANCELLABLE_SHIPMENT_STATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede cancelar un envio en estado {shipment.status.value}",
        )

    # Segundo lock, siempre despues del Shipment. Vehicle y Driver se bloquean
    # implicitamente con su UPDATE al hacer flush, ya con ambos locks tomados.
    order = db.query(Order).filter(Order.id == order_id).with_for_update().first()

    # Estado terminal: libera exclusivamente el Vehicle/Driver referenciados por
    # este shipment, fija actual_delivery y resetea delay_risk_score.
    apply_terminal_state(shipment, OrderStatus.cancelled, db)
    order.status = OrderStatus.cancelled

    db.commit()  # un solo commit: Shipment, Order, Vehicle y Driver
    db.refresh(order)
    # El evento se publica solo despues del commit (seccion 8). Se usa el id del
    # Shipment, no el del Order de la URL.
    publish_shipment_status_changed(shipment.id, OrderStatus.cancelled)
    return order
