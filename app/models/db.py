"""
SQLAlchemy models for Atumwa.
PostGIS is used for rider location so we can do fast nearest-neighbour queries.
"""
import enum
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ────────────────────────────────────────────────────────────────────

class VehicleType(str, enum.Enum):
    BIKE       = "bike"       # bicycle / motorcycle – small parcels
    CAR        = "car"        # sedan / hatchback – medium packages
    TRUCK      = "truck"      # pickup / lorry – large / bulk loads


class OrderStatus(str, enum.Enum):
    PENDING    = "pending"    # waiting for a rider to accept
    ACCEPTED   = "accepted"   # rider has accepted
    PICKED_UP  = "picked_up"  # rider collected the package
    DELIVERED  = "delivered"  # delivery confirmed
    CANCELLED  = "cancelled"  # cancelled by customer or timed out


class PaymentMethod(str, enum.Enum):
    ECOCASH    = "ecocash"
    CASH       = "cash"


# ── Tables ───────────────────────────────────────────────────────────────────

class Customer(Base):
    """Registered customers (auto-created on first contact)."""
    __tablename__ = "customers"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    phone        = Column(String(20), unique=True, nullable=False, index=True)
    name         = Column(String(120))
    created_at   = Column(DateTime, default=datetime.utcnow)
    is_active    = Column(Boolean, default=True)

    orders       = relationship("Order", back_populates="customer")


class Rider(Base):
    """Delivery riders / drivers who have registered via the bot."""
    __tablename__ = "riders"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    phone         = Column(String(20), unique=True, nullable=False, index=True)
    name          = Column(String(120), nullable=False)
    vehicle_type  = Column(Enum(VehicleType), nullable=False)
    plate_number  = Column(String(20))

    # PostGIS point – updated every time the rider pings their location
    location      = Column(Geography(geometry_type="POINT", srid=4326))
    last_seen_at  = Column(DateTime)

    is_online     = Column(Boolean, default=False)
    is_active     = Column(Boolean, default=True)  # set False to ban

    # Running average: updated after each completed delivery
    rating        = Column(Float, default=5.0)
    rating_count  = Column(Integer, default=0)

    created_at    = Column(DateTime, default=datetime.utcnow)

    orders        = relationship("Order", back_populates="rider")
    ratings       = relationship("Rating", back_populates="rider")


class Order(Base):
    """A single delivery request."""
    __tablename__ = "orders"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    customer_id     = Column(BigInteger, ForeignKey("customers.id"), nullable=False)
    rider_id        = Column(BigInteger, ForeignKey("riders.id"), nullable=True)

    # Locations stored as text (address string) AND geography point
    pickup_address  = Column(Text, nullable=False)
    pickup_location = Column(Geography(geometry_type="POINT", srid=4326))

    dropoff_address = Column(Text, nullable=False)
    dropoff_location= Column(Geography(geometry_type="POINT", srid=4326))

    package_type    = Column(String(60))   # e.g. "parcel", "document", "groceries"
    package_notes   = Column(Text)

    payment_method  = Column(Enum(PaymentMethod))
    ecocash_number  = Column(String(20))   # nullable – only if EcoCash chosen
    estimated_price = Column(Float)        # calculated by bot (Phase 2)

    status          = Column(Enum(OrderStatus), default=OrderStatus.PENDING)

    created_at      = Column(DateTime, default=datetime.utcnow)
    accepted_at     = Column(DateTime)
    delivered_at    = Column(DateTime)

    customer        = relationship("Customer", back_populates="orders")
    rider           = relationship("Rider", back_populates="orders")
    rating          = relationship("Rating", back_populates="order", uselist=False)


class Rating(Base):
    """Post-delivery rating left by the customer."""
    __tablename__ = "ratings"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id   = Column(BigInteger, ForeignKey("orders.id"), unique=True, nullable=False)
    rider_id   = Column(BigInteger, ForeignKey("riders.id"), nullable=False)
    stars      = Column(Integer, nullable=False)   # 1–5
    comment    = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    order      = relationship("Order", back_populates="rating")
    rider      = relationship("Rider", back_populates="ratings")
