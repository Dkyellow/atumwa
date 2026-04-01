"""
Atumwa conversation state machine.

Every incoming WhatsApp message hits handle_message().
The function reads the current session state, processes
the message, updates state, and returns a reply string.

States (customer flow):
  START → AWAITING_PICKUP → AWAITING_DROPOFF →
  AWAITING_PACKAGE_TYPE → AWAITING_NOTES →
  AWAITING_PAYMENT → AWAITING_PAYMENT_NUMBER (EcoCash only) →
  SHOWING_RIDERS → IN_RELAY

States (rider flow – triggered by keyword "rider"):
  START → RIDER_REG_NAME → RIDER_REG_VEHICLE → RIDER_REG_PLATE →
  RIDER_ACTIVE (rider is now online; pings location)
"""
import logging
from typing import Any

from app.core.session import clear_session, get_session, save_session

log = logging.getLogger(__name__)

# ── Step constants ────────────────────────────────────────────────────────────
START                  = "START"
AWAITING_PICKUP        = "AWAITING_PICKUP"
AWAITING_DROPOFF       = "AWAITING_DROPOFF"
AWAITING_PACKAGE_TYPE  = "AWAITING_PACKAGE_TYPE"
AWAITING_NOTES         = "AWAITING_NOTES"
AWAITING_PAYMENT       = "AWAITING_PAYMENT"
AWAITING_ECOCASH_NUM   = "AWAITING_ECOCASH_NUM"
SHOWING_RIDERS         = "SHOWING_RIDERS"
IN_RELAY               = "IN_RELAY"

RIDER_REG_NAME         = "RIDER_REG_NAME"
RIDER_REG_VEHICLE      = "RIDER_REG_VEHICLE"
RIDER_REG_PLATE        = "RIDER_REG_PLATE"
RIDER_ACTIVE           = "RIDER_ACTIVE"

PACKAGE_TYPES = {
    "1": "Document / envelope",
    "2": "Small parcel",
    "3": "Groceries / shopping",
    "4": "Large / heavy package",
}

VEHICLE_TYPES = {
    "1": "bike",
    "2": "car",
    "3": "truck",
}


# ── Main entry point ──────────────────────────────────────────────────────────

async def handle_message(
    phone: str,
    text: str,
    location: dict | None = None,   # {"lat": ..., "lon": ...} if user pinned location
    db=None,                         # AsyncSession – injected from router
) -> str | list[str]:
    """
    Process an incoming message and return a reply (or list of replies).
    All side-effects (DB writes) are done via service helpers imported lazily
    to avoid circular imports.
    """
    session: dict[str, Any] = await get_session(phone)
    step: str = session.get("step", START)
    text = text.strip()

    log.info("handle_message phone=%s step=%s text=%r", phone, step, text)

    # ── Global escape hatches ─────────────────────────────────────────────────
    if text.lower() in ("cancel", "stop", "quit"):
        await clear_session(phone)
        return (
            "❌ Order cancelled. Send *Hi* anytime to start a new delivery."
        )

    if text.lower() in ("help", "menu"):
        return _help_text()

    # ── Route by current step ─────────────────────────────────────────────────
    if step == START:
        return await _step_start(phone, text, session, db)

    # ── Customer flow ─────────────────────────────────────────────────────────
    if step == AWAITING_PICKUP:
        return await _step_pickup(phone, text, location, session)

    if step == AWAITING_DROPOFF:
        return await _step_dropoff(phone, text, location, session)

    if step == AWAITING_PACKAGE_TYPE:
        return await _step_package_type(phone, text, session)

    if step == AWAITING_NOTES:
        return await _step_notes(phone, text, session)

    if step == AWAITING_PAYMENT:
        return await _step_payment(phone, text, session)

    if step == AWAITING_ECOCASH_NUM:
        return await _step_ecocash_number(phone, text, session, db)

    if step == SHOWING_RIDERS:
        return await _step_pick_rider(phone, text, session, db)

    if step == IN_RELAY:
        return await _step_relay(phone, text, session)

    # ── Rider registration flow ───────────────────────────────────────────────
    if step == RIDER_REG_NAME:
        return await _step_rider_name(phone, text, session)

    if step == RIDER_REG_VEHICLE:
        return await _step_rider_vehicle(phone, text, session)

    if step == RIDER_REG_PLATE:
        return await _step_rider_plate(phone, text, session, db)

    if step == RIDER_ACTIVE:
        return await _step_rider_active(phone, text, location, session, db)

    # Fallback
    await clear_session(phone)
    return "Something went wrong. Send *Hi* to start again."


# ── Step handlers ─────────────────────────────────────────────────────────────

async def _step_start(phone, text, session, db) -> str:
    txt = text.lower()

    # Rider registration path
    if txt in ("rider", "driver", "join as rider"):
        session["step"] = RIDER_REG_NAME
        session["role"] = "rider"
        await save_session(phone, session)
        return (
            "🏍️ *Welcome to Atumwa Rider Registration!*\n\n"
            "What is your full name?"
        )

    # Check if this phone is already a registered rider going online
    from app.services.rider_service import get_rider_by_phone
    if db:
        rider = await get_rider_by_phone(db, phone)
        if rider:
            session["step"] = RIDER_ACTIVE
            session["role"] = "rider"
            session["rider_id"] = rider.id
            await save_session(phone, session)
            return (
                f"👋 Welcome back, *{rider.name}*!\n\n"
                "You are now *online* ✅\n"
                "Please share your current location so we can match you with nearby orders.\n\n"
                "_Tip: Pin your location in WhatsApp → Attach → Location_"
            )

    # Default: start a delivery order
    session["step"] = AWAITING_PICKUP
    session["role"] = "customer"
    await save_session(phone, session)
    return (
        "🛵 *Welcome to Atumwa Delivery!*\n\n"
        "Let's get your package moving.\n\n"
        "📍 *Where should we pick it up?*\n"
        "Type an address _or_ share your location pin."
    )


async def _step_pickup(phone, text, location, session) -> str:
    if location:
        session["pickup_address"] = f"Pin: {location['lat']},{location['lon']}"
        session["pickup_lat"]     = location["lat"]
        session["pickup_lon"]     = location["lon"]
    else:
        session["pickup_address"] = text

    session["step"] = AWAITING_DROPOFF
    await save_session(phone, session)
    return (
        f"✅ Pickup: _{session['pickup_address']}_\n\n"
        "📍 *Where should we deliver to?*\n"
        "Type an address or share a location pin."
    )


async def _step_dropoff(phone, text, location, session) -> str:
    if location:
        session["dropoff_address"] = f"Pin: {location['lat']},{location['lon']}"
        session["dropoff_lat"]     = location["lat"]
        session["dropoff_lon"]     = location["lon"]
    else:
        session["dropoff_address"] = text

    session["step"] = AWAITING_PACKAGE_TYPE
    await save_session(phone, session)

    options = "\n".join(f"*{k}* – {v}" for k, v in PACKAGE_TYPES.items())
    return (
        f"✅ Drop-off: _{session['dropoff_address']}_\n\n"
        "📦 *What are you sending?* Reply with a number:\n\n"
        f"{options}"
    )


async def _step_package_type(phone, text, session) -> str:
    if text not in PACKAGE_TYPES:
        options = "\n".join(f"*{k}* – {v}" for k, v in PACKAGE_TYPES.items())
        return f"Please reply with *1*, *2*, *3*, or *4*:\n\n{options}"

    session["package_type"] = PACKAGE_TYPES[text]
    session["step"]         = AWAITING_NOTES
    await save_session(phone, session)
    return (
        f"✅ Package type: _{session['package_type']}_\n\n"
        "📝 Any special instructions for the rider?\n"
        "_(e.g. fragile, leave at gate, call on arrival)_\n\n"
        "Or type *skip* to continue."
    )


async def _step_notes(phone, text, session) -> str:
    session["notes"] = "" if text.lower() == "skip" else text
    session["step"]  = AWAITING_PAYMENT
    await save_session(phone, session)
    return (
        "💳 *How would you like to pay?*\n\n"
        "*1* – EcoCash\n"
        "*2* – Cash on delivery"
    )


async def _step_payment(phone, text, session) -> str:
    if text == "1":
        session["payment"] = "ecocash"
        session["step"]    = AWAITING_ECOCASH_NUM
        await save_session(phone, session)
        return "📱 Please enter your *EcoCash number* (e.g. 0771234567):"

    if text == "2":
        session["payment"] = "cash"
        return await _finalize_order(phone, session)

    return "Please reply *1* for EcoCash or *2* for Cash."


async def _step_ecocash_number(phone, text, session, db) -> str:
    # Basic Zim number validation
    cleaned = text.replace(" ", "").replace("-", "")
    if not (cleaned.startswith(("077", "078", "071")) and len(cleaned) == 10):
        return (
            "That doesn't look like a valid Zimbabwean number.\n"
            "Please enter a number like *0771234567*:"
        )
    session["ecocash_number"] = cleaned
    return await _finalize_order(phone, session, db)


async def _finalize_order(phone, session, db=None) -> str:
    """
    Save the order to the database and show the order summary.
    Rider matching happens in the next step (_step_pick_rider).
    """
    from app.services.order_service import create_order
    from app.services.rider_service import find_nearest_riders

    order_id = None
    riders   = []

    if db:
        order = await create_order(db, phone, session)
        order_id = order.id

        if session.get("pickup_lat"):
            riders = await find_nearest_riders(
                db,
                lat=session["pickup_lat"],
                lon=session["pickup_lon"],
                package_type=session["package_type"],
                limit=5,
            )

    session["step"]     = SHOWING_RIDERS
    session["order_id"] = order_id
    session["rider_candidates"] = [
        {"id": r.id, "name": r.name, "rating": r.rating, "vehicle": r.vehicle_type}
        for r in riders
    ] if riders else []
    await save_session(phone, session)

    # Order summary
    summary = (
        "📋 *Order Summary*\n"
        f"📍 Pickup:   _{session['pickup_address']}_\n"
        f"📍 Drop-off: _{session['dropoff_address']}_\n"
        f"📦 Package:  _{session['package_type']}_\n"
        f"💳 Payment:  _{session.get('ecocash_number', 'Cash on delivery')}_\n"
    )
    if session.get("notes"):
        summary += f"📝 Notes: _{session['notes']}_\n"

    if not session["rider_candidates"]:
        return (
            summary + "\n"
            "⏳ No riders available right now near your pickup.\n"
            "We'll notify you as soon as one is nearby!\n\n"
            "_We're searching… sit tight 🙏_"
        )

    rider_list = "\n".join(
        f"*{i+1}* – {r['name']} {'🏍️' if r['vehicle']=='bike' else '🚗'} "
        f"⭐ {r['rating']:.1f}"
        for i, r in enumerate(session["rider_candidates"])
    )

    return (
        summary + "\n"
        "🔍 *Here are your nearest riders:*\n\n"
        f"{rider_list}\n\n"
        "Reply with the *number* of the rider you'd like, or *0* to let Atumwa auto-assign."
    )


async def _step_pick_rider(phone, text, session, db) -> str:
    candidates = session.get("rider_candidates", [])

    if text == "0":
        chosen = candidates[0] if candidates else None
    elif text.isdigit() and 1 <= int(text) <= len(candidates):
        chosen = candidates[int(text) - 1]
    else:
        return f"Please reply with a number between *1* and *{len(candidates)}*, or *0* to auto-assign."

    if not chosen:
        return "No riders found. We'll notify you when one becomes available."

    from app.services.order_service import assign_rider
    from app.core.session import set_relay, get_session, save_session

    rider_phone = None
    if db:
        await assign_rider(db, session["order_id"], chosen["id"])
        from app.services.rider_service import get_rider_by_id
        rider = await get_rider_by_id(db, chosen["id"])
        rider_phone = rider.phone if rider else None

    if rider_phone:
        await set_relay(phone, rider_phone)

        # Update both sessions
        session["step"]       = IN_RELAY
        session["relay_with"] = rider_phone
        await save_session(phone, session)

        rider_session = await get_session(rider_phone)
        rider_session["step"]       = IN_RELAY
        rider_session["relay_with"] = phone
        rider_session["order_id"]   = session["order_id"]
        await save_session(rider_phone, rider_session)

    return (
        f"✅ *{chosen['name']}* is on the way!\n\n"
        "You are now connected. You can message the rider directly here.\n"
        "Type *done* when the delivery is complete.\n\n"
        "🔒 _Your number is private — all messages go through Atumwa._"
    )


async def _step_relay(phone, text, session) -> str:
    """
    In relay mode every message from this phone gets forwarded to
    the other party. The actual forwarding is done in the webhook
    router after this function returns the reply.
    We return a special sentinel so the router knows to forward.
    """
    if text.lower() == "done":
        return "__RELAY_DONE__"
    return "__RELAY_FORWARD__"


# ── Rider flow ────────────────────────────────────────────────────────────────

async def _step_rider_name(phone, text, session) -> str:
    if len(text) < 2:
        return "Please enter your full name:"
    session["rider_name"] = text
    session["step"]       = RIDER_REG_VEHICLE
    await save_session(phone, session)
    options = "\n".join(f"*{k}* – {v}" for k, v in VEHICLE_TYPES.items())
    return (
        f"Nice to meet you, *{text}*! 👋\n\n"
        "🚗 *What vehicle do you use?*\n\n"
        f"{options}"
    )


async def _step_rider_vehicle(phone, text, session) -> str:
    if text not in VEHICLE_TYPES:
        return "Please reply *1* (bike), *2* (car), or *3* (truck)."
    session["rider_vehicle"] = VEHICLE_TYPES[text]
    session["step"]          = RIDER_REG_PLATE
    await save_session(phone, session)
    return (
        f"✅ Vehicle: _{session['rider_vehicle']}_\n\n"
        "🔢 Enter your vehicle plate number (or type *none* if no plate):"
    )


async def _step_rider_plate(phone, text, session, db) -> str:
    session["rider_plate"] = "" if text.lower() == "none" else text.upper()

    from app.services.rider_service import register_rider
    if db:
        await register_rider(
            db,
            phone=phone,
            name=session["rider_name"],
            vehicle_type=session["rider_vehicle"],
            plate=session["rider_plate"],
        )

    session["step"] = RIDER_ACTIVE
    await save_session(phone, session)

    return (
        "🎉 *You're registered with Atumwa!*\n\n"
        "You'll receive job alerts when customers need delivery near you.\n\n"
        "📍 Please share your *current location* to go online:\n"
        "_WhatsApp → Attach → Location_"
    )


async def _step_rider_active(phone, text, location, session, db) -> str:
    if location:
        from app.services.rider_service import update_rider_location
        if db:
            await update_rider_location(
                db,
                phone=phone,
                lat=location["lat"],
                lon=location["lon"],
            )
        return (
            "📍 Location updated! You are *online* ✅\n"
            "We'll ping you when there's a delivery near you.\n\n"
            "_Share your location again anytime to update it._\n"
            "_Type *offline* to go offline._"
        )

    if text.lower() == "offline":
        from app.services.rider_service import set_rider_offline
        if db:
            await set_rider_offline(db, phone)
        await clear_session(phone)
        return "You are now *offline*. Send *Hi* when you're ready again. 👋"

    return (
        "Share your *location* to stay online, or type *offline* to go offline."
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _help_text() -> str:
    return (
        "🛵 *Atumwa Delivery Bot*\n\n"
        "*Send a delivery:* Say _Hi_ or _Hello_\n"
        "*Join as a rider:* Type _rider_\n"
        "*Cancel an order:* Type _cancel_\n"
        "*This menu:* Type _help_\n\n"
        "🇿🇼 Serving Harare, Zimbabwe"
    )
