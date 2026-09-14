"""HubSpot tools — HubSpot API v3 integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from agentspan.agents import tool

_BASE_URL = "https://api.hubapi.com"


def _get_token() -> str:
    token = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("HUBSPOT_ACCESS_TOKEN environment variable is not set")
    return token


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


@tool(credentials=["HUBSPOT_ACCESS_TOKEN"])
def hubspot_search_contacts(query: str) -> List[Dict[str, Any]]:
    """Search HubSpot contacts.

    Args:
        query: Search query string (matches against name, email, etc.).

    Returns:
        List of contact objects with ``id``, ``email``, ``firstname``, ``lastname``.
    """
    if not query:
        raise ValueError("query is required")

    payload = {
        "query": query,
        "limit": 20,
        "properties": ["email", "firstname", "lastname", "phone", "company"],
    }

    resp = httpx.post(
        f"{_BASE_URL}/crm/v3/objects/contacts/search",
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    results = []
    for item in data.get("results", []):
        props = item.get("properties", {})
        results.append({
            "id": item.get("id", ""),
            "email": props.get("email", ""),
            "firstname": props.get("firstname", ""),
            "lastname": props.get("lastname", ""),
        })
    return results


@tool(credentials=["HUBSPOT_ACCESS_TOKEN"])
def hubspot_get_contact(contact_id: str) -> Dict[str, Any]:
    """Get details of a HubSpot contact.

    Args:
        contact_id: The HubSpot contact ID.

    Returns:
        Contact object with properties.
    """
    if not contact_id:
        raise ValueError("contact_id is required")

    resp = httpx.get(
        f"{_BASE_URL}/crm/v3/objects/contacts/{contact_id}",
        params={"properties": "email,firstname,lastname,phone,company"},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return {
        "id": data.get("id", ""),
        "properties": data.get("properties", {}),
    }


@tool(credentials=["HUBSPOT_ACCESS_TOKEN"])
def hubspot_list_deals(limit: int = 20) -> List[Dict[str, Any]]:
    """List HubSpot deals.

    Args:
        limit: Maximum number of deals (default 20).

    Returns:
        List of deal objects with ``id``, ``dealname``, ``amount``, ``dealstage``.
    """
    _get_token()
    limit = min(max(limit, 1), 100)

    resp = httpx.get(
        f"{_BASE_URL}/crm/v3/objects/deals",
        params={"limit": limit, "properties": "dealname,amount,dealstage,closedate"},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    results = []
    for item in data.get("results", []):
        props = item.get("properties", {})
        results.append({
            "id": item.get("id", ""),
            "dealname": props.get("dealname", ""),
            "amount": props.get("amount", ""),
            "dealstage": props.get("dealstage", ""),
        })
    return results


@tool(credentials=["HUBSPOT_ACCESS_TOKEN"])
def hubspot_get_deal(deal_id: str) -> Dict[str, Any]:
    """Get details of a HubSpot deal.

    Args:
        deal_id: The HubSpot deal ID.

    Returns:
        Deal object with properties.
    """
    if not deal_id:
        raise ValueError("deal_id is required")

    resp = httpx.get(
        f"{_BASE_URL}/crm/v3/objects/deals/{deal_id}",
        params={"properties": "dealname,amount,dealstage,closedate,pipeline"},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return {
        "id": data.get("id", ""),
        "properties": data.get("properties", {}),
    }


@tool(credentials=["HUBSPOT_ACCESS_TOKEN"])
def hubspot_create_contact(
    email: str, firstname: str = "", lastname: str = ""
) -> Dict[str, str]:
    """Create a new HubSpot contact.

    Args:
        email: Contact email address.
        firstname: Contact first name.
        lastname: Contact last name.

    Returns:
        Dict with ``id`` of the created contact.
    """
    if not email:
        raise ValueError("email is required")

    properties: Dict[str, str] = {"email": email}
    if firstname:
        properties["firstname"] = firstname
    if lastname:
        properties["lastname"] = lastname

    resp = httpx.post(
        f"{_BASE_URL}/crm/v3/objects/contacts",
        json={"properties": properties},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return {"id": data.get("id", "")}


def get_tools() -> List[Any]:
    """Return all hubspot tools."""
    return [hubspot_search_contacts, hubspot_get_contact, hubspot_list_deals, hubspot_get_deal, hubspot_create_contact]
