"""
Rider-related database operations.
"""
from datetime import datetime

from geoalchemy2.functions import ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Rider, VehicleType


async def get_rider_by_phone(db: AsyncSession, phone: str) -> Rider | None:
    result = await db.execute(select(Rider).where(Rider.phone == phone))
    return result.scalar_one_or_none()


async def get_rider_by_id(db: AsyncSession, rider_id: int) -> Rider | None:
    result = await db.execute(select(Rider).where(Rider.id == rider_id))
    return result.scalar_one_or_none()


async def register_rider(
    db: AsyncSession,
    phone: str,
    name: str,
    vehicle_type: str,
    plate: str,
) -> Rider:
    # Map string → enum
    vt_map = {"bike": VehicleType.BIKE, "car": VehicleType.CAR, "truck": VehicleType.TRUCK}

    existing = await get_rider_by_phone(db, phone)
    if existing:
        # Re-registration: update details
        existing.name         = name
        existing.vehicle_type = vt_map[vehicle_type]
        existing.plate_number = plate
        existing.is_active    = True
        await db.commit()
        await db.refresh(existing)
        return existing

    rider = Rider(
        phone        = phone,
        name         = name,
        vehicle_type = vt_map[vehicle_type],
        plate_number = plate,
        is_active    = True,
    )
    db.add(rider)
    await db.commit()
    await db.refresh(rider)
    return rider


async def update_rider_location(db: AsyncSession, phone: str, lat: float, lon: float) -> None:
    """Update the rider's PostGIS location and mark them online."""
    point = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
    await db.execute(
        update(Rider)
        .where(Rider.phone == phone)
        .values(
            location=point,
            last_seen_at=datetime.utcnow(),
            is_online=True,
        )
    )
    await db.commit()


async def set_rider_offline(db: AsyncSession, phone: str) -> None:
    await db.execute(
        update(Rider).where(Rider.phone == phone).values(is_online=False)
    )
    await db.commit()


async def find_nearest_riders(
    db: AsyncSession,
    lat: float,
    lon: float,
    package_type: str,
    limit: int = 5,
    radius_km: float = 10.0,
) -> list[Rider]:
    """
    Find up to `limit` online riders within `radius_km` km of (lat, lon),
    filtered by vehicle suitability for the package type, ordered by distance.
    """
    # Determine which vehicle types can handle this package
    if "large" in package_type.lower() or "heavy" in package_type.lower():
        suitable = [VehicleType.TRUCK, VehicleType.CAR]
    elif "groceries" in package_type.lower():
        suitable = [VehicleType.CAR, VehicleType.TRUCK, VehicleType.BIKE]
    else:
        suitable = [VehicleType.BIKE, VehicleType.CAR, VehicleType.TRUCK]

    point = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
    radius_m = radius_km * 1000

    result = await db.execute(
        select(Rider)
        .where(
            Rider.is_online == True,
            Rider.is_active == True,
            Rider.vehicle_type.in_(suitable),
            ST_DWithin(Rider.location, point, radius_m),
        )
        .order_by(Rider.rating.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_rider_rating(db: AsyncSession, rider_id: int, new_stars: int) -> None:
    """Recalculate running average rating after a new review."""
    rider = await get_rider_by_id(db, rider_id)
    if not rider:
        return
    total        = rider.rating * rider.rating_count + new_stars
    rider.rating_count += 1
    rider.rating = round(total / rider.rating_count, 2)
    await db.commit()
