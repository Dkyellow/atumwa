"""
FastAPI router that handles the Meta WhatsApp Cloud API webhook.

Two endpoints:
  GET  /webhook  – verification challenge (called once when you set up the webhook)
  POST /webhook  – incoming messages
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.session import clear_relay, clear_session, get_relay_target, get_session, save_session
from app.services import whatsapp
from app.services.bot import IN_RELAY, handle_message

log = logging.getLogger(__name__)
router = APIRouter()


# ── Webhook verification ──────────────────────────────────────────────────────

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str       = Query(alias="hub.mode", default=""),
    hub_challenge: str  = Query(alias="hub.challenge", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        log.info("Webhook verified ✅")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


# ── Incoming messages ─────────────────────────────────────────────────────────

@router.post("/webhook")
async def receive_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body: dict[str, Any] = await request.json()
    log.debug("Webhook payload: %s", body)

    try:
        entry    = body["entry"][0]
        change   = entry["changes"][0]["value"]
        messages = change.get("messages", [])
    except (KeyError, IndexError):
        # Meta sends other event types (status updates etc.) – ignore silently
        return {"status": "ok"}

    for msg in messages:
        await _process_message(msg, db)

    return {"status": "ok"}


async def _process_message(msg: dict, db: AsyncSession) -> None:
    phone      = msg["from"]            # e.g. "263771234567"
    message_id = msg.get("id", "")
    msg_type   = msg.get("type", "")

    # Mark as read (blue ticks)
    await whatsapp.mark_as_read(message_id)

    # Extract text content
    text     = ""
    location = None

    if msg_type == "text":
        text = msg["text"]["body"]

    elif msg_type == "interactive":
        # Button / list reply
        interactive = msg["interactive"]
        if interactive["type"] == "button_reply":
            text = interactive["button_reply"]["id"]
        elif interactive["type"] == "list_reply":
            text = interactive["list_reply"]["id"]

    elif msg_type == "location":
        loc      = msg["location"]
        location = {"lat": loc["latitude"], "lon": loc["longitude"]}
        text     = f"📍 {loc.get('name', 'Location shared')}"

    elif msg_type in ("image", "document", "audio", "video"):
        text = f"[{msg_type} received]"

    else:
        return  # Ignore unsupported types

    # ── Relay mode: forward messages between customer ↔ rider ─────────────────
    session = await get_session(phone)
    if session.get("step") == IN_RELAY:
        await _handle_relay(phone, text, session, db)
        return

    # ── Normal bot flow ───────────────────────────────────────────────────────
    reply = await handle_message(phone=phone, text=text, location=location, db=db)

    if isinstance(reply, list):
        for r in reply:
            await whatsapp.send_text(phone, r)
    else:
        await whatsapp.send_text(phone, reply)


async def _handle_relay(phone: str, text: str, session: dict, db: AsyncSession) -> None:
    """
    Route messages between customer and rider.
    We figure out the role by checking which relay key exists.
    """
    # Try customer key first, then rider key
    target = await get_relay_target(phone, "c")
    role   = "customer"
    if not target:
        target = await get_relay_target(phone, "r")
        role   = "rider"

    reply = await handle_message(phone=phone, text=text, db=db)

    if reply == "__RELAY_DONE__":
        # Delivery marked complete — close the relay, prompt for rating
        await _close_relay(phone, target, session, db, role)
        return

    if reply == "__RELAY_FORWARD__" and target:
        # Forward the message to the other party with a label
        label = "🛵 Rider" if role == "customer" else "📦 Customer"
        await whatsapp.send_text(target, f"{label}: {text}")
        # Confirm to sender
        await whatsapp.send_text(phone, "✅ _Message sent_")
    else:
        await whatsapp.send_text(phone, reply)


async def _close_relay(phone, target, session, db, role) -> None:
    """Mark delivery done and ask for rating (from customer side)."""
    from app.services.order_service import complete_order

    order_id = session.get("order_id")
    if order_id and db:
        await complete_order(db, order_id)

    if target:
        await whatsapp.send_text(
            target,
            "✅ Delivery marked as complete by the other party. Thank you! 🎉"
        )

    await whatsapp.send_text(
        phone,
        "✅ *Delivery complete!*\n\n"
        "Please rate your rider:\n"
        "*1* ⭐  *2* ⭐⭐  *3* ⭐⭐⭐  *4* ⭐⭐⭐⭐  *5* ⭐⭐⭐⭐⭐"
    )

    # Switch to rating state
    session["step"]       = "AWAITING_RATING"
    session["relay_with"] = target
    await save_session(phone, session)

    if target:
        target_session = await get_session(target)
        await clear_session(target)
        c_phone = phone if role == "customer" else target
        r_phone = target if role == "customer" else phone
        await clear_relay(c_phone, r_phone)
