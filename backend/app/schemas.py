import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import OrderPriority, OrderStatus


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
