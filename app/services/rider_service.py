"""
Rider-related database operations.
Uses plain Haversine distance instead of PostGIS.
"""
import math
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Rider, VehicleType


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Straight-line distance between two lat/lon points in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


async def get_rider_by_phone(db: AsyncSession, phone: str) -> Rider | None:
    result = await db.execute(select(Rider).where(Rider.phone == phone))
    return result.scalar_one_or_none()


async def get_rider_by_id(db: AsyncSession, rider_id: int) -> Rider | None:
    result = await db.execute(select(Rider).where(Rider.id == rider_id))
    return result.scalar_one_or_none()


async def register_rider(db: AsyncSession, phone: str, name: str, vehicle_type: str, plate: str) -> Rider:
    vt_map = {"bike": VehicleType.BIKE, "car": VehicleType.CAR, "truck": VehicleType.TRUCK}

    existing = await get_rider_by_phone(db, phone)
    if existing:
        existing.name         = name
        existing.vehicle_type = vt_map[vehicle_type]
        existing.plate_number = plate
        existing.is_active    = True
        await db.commit()
        await db.refresh(existing)
        return existing

    rider = Rider(
        phone=phone, name=name,
        vehicle_type=vt_map[vehicle_type],
        plate_number=plate, is_active=True,
    )
    db.add(rider)
    await db.commit()
    await db.refresh(rider)
    return rider


async def update_rider_location(db: AsyncSession, phone: str, lat: float, lon: float) -> None:
    await db.execute(
        update(Rider).where(Rider.phone == phone).values(
            lat=lat, lon=lon,
            last_seen_at=datetime.utcnow(),
            is_online=True,
        )
    )
    await db.commit()


async def set_rider_offline(db: AsyncSession, phone: str) -> None:
    await db.execute(update(Rider).where(Rider.phone == phone).values(is_online=False))
    await db.commit()


async def find_nearest_riders(
    db: AsyncSession,
    lat: float | None,
    lon: float | None,
    package_type: str,
    limit: int = 5,
    radius_km: float = 15.0,
) -> list[Rider]:
    """
    Find nearest online riders.
    If no coordinates provided, return all online riders sorted by rating.
    """
    if "large" in package_type.lower() or "heavy" in package_type.lower():
        suitable = [VehicleType.TRUCK, VehicleType.CAR]
    elif "groceries" in package_type.lower():
        suitable = [VehicleType.CAR, VehicleType.TRUCK, VehicleType.BIKE]
    else:
        suitable = [VehicleType.BIKE, VehicleType.CAR, VehicleType.TRUCK]

    result = await db.execute(
        select(Rider).where(
            Rider.is_online == True,
            Rider.is_active == True,
            Rider.vehicle_type.in_(suitable),
        ).order_by(Rider.rating.desc())
    )
    all_riders = list(result.scalars().all())

    # If no customer coordinates — return all online riders
    if lat is None or lon is None:
        return all_riders[:limit]

    # Filter by Haversine distance
    nearby = [
        r for r in all_riders
        if r.lat is not None and r.lon is not None
        and _haversine_km(lat, lon, r.lat, r.lon) <= radius_km
    ]

    # Fallback: if no riders within radius, return all online riders anyway
    if not nearby:
        return all_riders[:limit]

    return nearby[:limit]


async def update_rider_rating(db: AsyncSession, rider_id: int, new_stars: int) -> None:
    rider = await get_rider_by_id(db, rider_id)
    if not rider:
        return
    total = rider.rating * rider.rating_count + new_stars
    rider.rating_count += 1
    rider.rating = round(total / rider.rating_count, 2)
    await db.commit()
