"""
SQLAlchemy models for Atumwa.
Locations stored as plain lat/lon float columns (no PostGIS required).
"""
import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class VehicleType(str, enum.Enum):
    BIKE  = "bike"
    CAR   = "car"
    TRUCK = "truck"


class OrderStatus(str, enum.Enum):
    PENDING   = "pending"
    ACCEPTED  = "accepted"
    PICKED_UP = "picked_up"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(str, enum.Enum):
    ECOCASH = "ecocash"
    CASH    = "cash"


# ── Tables ────────────────────────────────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    phone      = Column(String(20), unique=True, nullable=False, index=True)
    name       = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active  = Column(Boolean, default=True)

    orders     = relationship("Order", back_populates="customer")


class Rider(Base):
    __tablename__ = "riders"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    phone        = Column(String(20), unique=True, nullable=False, index=True)
    name         = Column(String(120), nullable=False)
    vehicle_type = Column(Enum(VehicleType), nullable=False)
    plate_number = Column(String(20))

    # Plain lat/lon — no PostGIS needed
    lat          = Column(Float)
    lon          = Column(Float)
    last_seen_at = Column(DateTime)

    is_online    = Column(Boolean, default=False)
    is_active    = Column(Boolean, default=True)

    rating       = Column(Float, default=5.0)
    rating_count = Column(Integer, default=0)

    created_at   = Column(DateTime, default=datetime.utcnow)

    orders       = relationship("Order", back_populates="rider")
    ratings      = relationship("Rating", back_populates="rider")


class Order(Base):
    __tablename__ = "orders"

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    customer_id      = Column(BigInteger, ForeignKey("customers.id"), nullable=False)
    rider_id         = Column(BigInteger, ForeignKey("riders.id"), nullable=True)

    pickup_address   = Column(Text, nullable=False)
    pickup_lat       = Column(Float)
    pickup_lon       = Column(Float)

    dropoff_address  = Column(Text, nullable=False)
    dropoff_lat      = Column(Float)
    dropoff_lon      = Column(Float)

    package_type     = Column(String(60))
    package_notes    = Column(Text)

    payment_method   = Column(Enum(PaymentMethod))
    ecocash_number   = Column(String(20))
    estimated_price  = Column(Float)

    status           = Column(Enum(OrderStatus), default=OrderStatus.PENDING)

    created_at       = Column(DateTime, default=datetime.utcnow)
    accepted_at      = Column(DateTime)
    delivered_at     = Column(DateTime)

    customer         = relationship("Customer", back_populates="orders")
    rider            = relationship("Rider", back_populates="orders")
    rating           = relationship("Rating", back_populates="order", uselist=False)


class Rating(Base):
    __tablename__ = "ratings"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id   = Column(BigInteger, ForeignKey("orders.id"), unique=True, nullable=False)
    rider_id   = Column(BigInteger, ForeignKey("riders.id"), nullable=False)
    stars      = Column(Integer, nullable=False)
    comment    = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    order      = relationship("Order", back_populates="rating")
    rider      = relationship("Rider", back_populates="ratings")
