"""
Thin wrapper around the Meta WhatsApp Cloud API.
All outgoing messages go through here.
"""
import logging

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

HEADERS = {
    "Authorization": f"Bearer {settings.whatsapp_access_token}",
    "Content-Type": "application/json",
}


async def send_text(to: str, message: str) -> None:
    """Send a plain text (with markdown) WhatsApp message."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message, "preview_url": False},
    }
    await _post(payload)


async def send_buttons(to: str, body: str, buttons: list[dict]) -> None:
    """
    Send an interactive button message (max 3 buttons).
    buttons: [{"id": "btn_1", "title": "Accept"}]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons[:3]
                ]
            },
        },
    }
    await _post(payload)


async def send_list(to: str, body: str, button_label: str, rows: list[dict]) -> None:
    """
    Send an interactive list message (up to 10 rows).
    rows: [{"id": "r1", "title": "Option 1", "description": "Details"}]
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": button_label,
                "sections": [{"title": "Options", "rows": rows[:10]}],
            },
        },
    }
    await _post(payload)


async def mark_as_read(message_id: str) -> None:
    """Mark a received message as read (shows blue ticks)."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    await _post(payload)


async def _post(payload: dict) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(settings.whatsapp_api_url, headers=HEADERS, json=payload)
        if resp.status_code != 200:
            log.error("WhatsApp API error %s: %s", resp.status_code, resp.text)
        else:
            log.debug("WhatsApp message sent: %s", resp.json())
