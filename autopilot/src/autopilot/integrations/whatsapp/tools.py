"""WhatsApp tools — WhatsApp Business Cloud API integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from agentspan.agents import tool

_BASE_URL = "https://graph.facebook.com/v18.0"


def _get_credentials() -> tuple[str, str]:
    token = os.environ.get("WHATSAPP_TOKEN", "")
    phone_id = os.environ.get("WHATSAPP_PHONE_ID", "")

    missing = []
    if not token:
        missing.append("WHATSAPP_TOKEN")
    if not phone_id:
        missing.append("WHATSAPP_PHONE_ID")

    if missing:
        raise RuntimeError(f"{', '.join(missing)} environment variable(s) not set")
    return token, phone_id


def _headers() -> Dict[str, str]:
    token, _ = _get_credentials()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _phone_id() -> str:
    _, phone_id = _get_credentials()
    return phone_id


@tool(credentials=["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"])
def whatsapp_send_message(to: str, text: str) -> Dict[str, Any]:
    """Send a text message via WhatsApp.

    Args:
        to: Recipient phone number in international format (e.g. ``"+1234567890"``).
        text: Message text.

    Returns:
        API response with message ID.
    """
    if not to:
        raise ValueError("to is required")
    if not text:
        raise ValueError("text is required")

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    resp = httpx.post(
        f"{_BASE_URL}/{_phone_id()}/messages",
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


@tool(credentials=["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"])
def whatsapp_send_template(
    to: str, template_name: str, parameters: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Send a template message via WhatsApp.

    Args:
        to: Recipient phone number in international format.
        template_name: Name of the approved message template.
        parameters: Optional list of parameter values for the template.

    Returns:
        API response with message ID.
    """
    if not to:
        raise ValueError("to is required")
    if not template_name:
        raise ValueError("template_name is required")

    template: Dict[str, Any] = {
        "name": template_name,
        "language": {"code": "en_US"},
    }
    if parameters:
        template["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in parameters],
            }
        ]

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": template,
    }

    resp = httpx.post(
        f"{_BASE_URL}/{_phone_id()}/messages",
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def get_tools() -> List[Any]:
    """Return all whatsapp tools."""
    return [whatsapp_send_message, whatsapp_send_template]
