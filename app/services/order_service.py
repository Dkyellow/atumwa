"""
Order-related database operations.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Customer, Order, OrderStatus, PaymentMethod, Rating


async def get_or_create_customer(db: AsyncSession, phone: str) -> Customer:
    result = await db.execute(select(Customer).where(Customer.phone == phone))
    customer = result.scalar_one_or_none()
    if customer:
        return customer
    customer = Customer(phone=phone)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def create_order(db: AsyncSession, phone: str, session: dict[str, Any]) -> Order:
    customer = await get_or_create_customer(db, phone)

    payment = (
        PaymentMethod.ECOCASH if session.get("payment") == "ecocash"
        else PaymentMethod.CASH
    )

    order = Order(
        customer_id     = customer.id,
        pickup_address  = session["pickup_address"],
        pickup_lat      = session.get("pickup_lat"),
        pickup_lon      = session.get("pickup_lon"),
        dropoff_address = session["dropoff_address"],
        dropoff_lat     = session.get("dropoff_lat"),
        dropoff_lon     = session.get("dropoff_lon"),
        package_type    = session["package_type"],
        package_notes   = session.get("notes", ""),
        payment_method  = payment,
        ecocash_number  = session.get("ecocash_number"),
        status          = OrderStatus.PENDING,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def assign_rider(db: AsyncSession, order_id: int, rider_id: int) -> None:
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order:
        order.rider_id    = rider_id
        order.status      = OrderStatus.ACCEPTED
        order.accepted_at = datetime.utcnow()
        await db.commit()


async def complete_order(db: AsyncSession, order_id: int) -> None:
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order:
        order.status       = OrderStatus.DELIVERED
        order.delivered_at = datetime.utcnow()
        await db.commit()


async def save_rating(db: AsyncSession, order_id: int, rider_id: int, stars: int, comment: str = "") -> Rating:
    rating = Rating(order_id=order_id, rider_id=rider_id, stars=stars, comment=comment)
    db.add(rating)
    await db.commit()
    await db.refresh(rating)

    from app.services.rider_service import update_rider_rating
    await update_rider_rating(db, rider_id, stars)
    return rating


async def get_order(db: AsyncSession, order_id: int) -> Order | None:
    result = await db.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()
