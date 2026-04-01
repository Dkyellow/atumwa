"""
Conversation state stored in Redis.

Each WhatsApp number gets a key:  session:{phone}
Value: JSON blob with the current step and collected data.

Sessions expire after 30 minutes of inactivity so
abandoned chatflows don't linger forever.
"""
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

SESSION_TTL = 60 * 30  # 30 minutes


_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def get_session(phone: str) -> dict[str, Any]:
    """Load the conversation session for a phone number."""
    r = get_redis()
    raw = await r.get(f"session:{phone}")
    if raw is None:
        return {}
    return json.loads(raw)


async def save_session(phone: str, data: dict[str, Any]) -> None:
    """Persist the session and reset the TTL."""
    r = get_redis()
    await r.setex(f"session:{phone}", SESSION_TTL, json.dumps(data))


async def clear_session(phone: str) -> None:
    """Delete the session (order placed or cancelled)."""
    r = get_redis()
    await r.delete(f"session:{phone}")


async def set_relay(customer_phone: str, rider_phone: str) -> None:
    """
    Store a bidirectional relay mapping so the bot can route
    messages between customer and rider.
    """
    r = get_redis()
    await r.setex(f"relay:c:{customer_phone}", SESSION_TTL * 4, rider_phone)
    await r.setex(f"relay:r:{rider_phone}", SESSION_TTL * 4, customer_phone)


async def get_relay_target(phone: str, role: str) -> str | None:
    """
    role: 'c' (customer) or 'r' (rider)
    Returns the OTHER party's phone number if a relay is active.
    """
    r = get_redis()
    return await r.get(f"relay:{role}:{phone}")


async def clear_relay(customer_phone: str, rider_phone: str) -> None:
    r = get_redis()
    await r.delete(f"relay:c:{customer_phone}", f"relay:r:{rider_phone}")
