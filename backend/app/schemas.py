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
