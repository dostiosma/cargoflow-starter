import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship

from app.database import Base
from app.db_types import GUID


class UserRole(str, enum.Enum):
    admin = "admin"
    driver = "driver"


class DriverStatus(str, enum.Enum):
    available = "available"
    busy = "busy"
    offline = "offline"


class VehicleType(str, enum.Enum):
    motocarro = "motocarro"
    van = "van"
    bicicleta = "bicicleta"


class VehicleStatus(str, enum.Enum):
    available = "available"
    in_use = "in_use"
    maintenance = "maintenance"


class OrderPriority(str, enum.Enum):
    normal = "normal"
    high = "high"
    critical = "critical"


class OrderStatus(str, enum.Enum):
    pending = "pending"
    assigned = "assigned"
    in_transit = "in_transit"
    delivered = "delivered"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    driver = relationship("Driver", back_populates="user", uselist=False)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    plate = Column(String, nullable=False)
    type = Column(SAEnum(VehicleType), nullable=False)
    capacity_kg = Column(Integer, nullable=False)
    status = Column(SAEnum(VehicleStatus), nullable=False, default=VehicleStatus.available)

    drivers = relationship("Driver", back_populates="vehicle")


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    vehicle_id = Column(GUID(), ForeignKey("vehicles.id"), nullable=True)
    status = Column(SAEnum(DriverStatus), nullable=False, default=DriverStatus.offline)

    user = relationship("User", back_populates="driver")
    vehicle = relationship("Vehicle", back_populates="drivers")


class Order(Base):
    __tablename__ = "orders"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    customer_name = Column(String, nullable=False)
    origin_address = Column(String, nullable=False)
    destination_address = Column(String, nullable=False)
    priority = Column(SAEnum(OrderPriority), nullable=False, default=OrderPriority.normal)
    status = Column(SAEnum(OrderStatus), nullable=False, default=OrderStatus.pending)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    shipment = relationship("Shipment", back_populates="order", uselist=False)


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    order_id = Column(GUID(), ForeignKey("orders.id"), nullable=False)
    vehicle_id = Column(GUID(), ForeignKey("vehicles.id"), nullable=True)
    driver_id = Column(GUID(), ForeignKey("drivers.id"), nullable=True)
    estimated_delivery = Column(DateTime, nullable=True)
    actual_delivery = Column(DateTime, nullable=True)
    status = Column(SAEnum(OrderStatus), nullable=False, default=OrderStatus.pending)
    delay_risk_score = Column(Float, nullable=True)

    order = relationship("Order", back_populates="shipment")
