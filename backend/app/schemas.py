import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import OrderPriority, OrderStatus, UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    created_at: datetime


class MeOut(BaseModel):
    # Spec seccion 7, GET /api/auth/me: unicamente estos cuatro campos.
    # id = User.id; driver_id = Driver.id asociado al usuario, o null (clave siempre presente).
    id: uuid.UUID
    email: str
    role: UserRole
    driver_id: uuid.UUID | None


class OrderCreate(BaseModel):
    customer_name: str
    origin_address: str
    destination_address: str
    priority: OrderPriority = OrderPriority.normal


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_name: str
    origin_address: str
    destination_address: str
    priority: OrderPriority
    status: OrderStatus
    created_at: datetime


from app.models import VehicleStatus, VehicleType


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plate: str
    type: VehicleType
    capacity_kg: int
    status: VehicleStatus


class VehicleStatusUpdate(BaseModel):
    status: VehicleStatus


from app.models import DriverStatus


class DriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    phone: str | None = None
    vehicle_id: uuid.UUID | None = None
    status: DriverStatus


from app.models import OrderStatus as ShipmentStatus


class ShipmentCreate(BaseModel):
    order_id: uuid.UUID


class ShipmentStatusUpdate(BaseModel):
    status: ShipmentStatus


class ShipmentRiskUpdate(BaseModel):
    # Seccion 7 del master spec: obligatorio, float dentro de 0-1 (extremos incluidos)
    delay_risk_score: float = Field(ge=0, le=1)


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    estimated_delivery: datetime | None = None
    actual_delivery: datetime | None = None
    status: ShipmentStatus
    delay_risk_score: float | None = None


class ShipmentAssignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None
    status: ShipmentStatus
    message: str


class DriverRouteOrderOut(BaseModel):
    # Spec seccion 7, GET /api/drivers/{id}/shipments: resumen minimo del Order.
    model_config = ConfigDict(from_attributes=True)

    customer_name: str
    origin_address: str
    destination_address: str
    priority: OrderPriority


class DriverRouteShipmentOut(BaseModel):
    # Esquema propio de la ruta del conductor (ShipmentOut no se reutiliza).
    # assigned_at y estimated_delivery son obligatorios, como en el spec;
    # actual_delivery siempre esta presente y vale null mientras no hay entrega.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ShipmentStatus
    assigned_at: datetime
    estimated_delivery: datetime
    actual_delivery: datetime | None
    order: DriverRouteOrderOut
