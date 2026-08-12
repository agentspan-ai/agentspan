"""Salesforce tools — Salesforce REST API integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from agentspan.agents import tool

_API_VERSION = "v59.0"


def _get_credentials() -> tuple[str, str]:
    instance_url = os.environ.get("SALESFORCE_INSTANCE_URL", "")
    token = os.environ.get("SALESFORCE_ACCESS_TOKEN", "")

    missing = []
    if not instance_url:
        missing.append("SALESFORCE_INSTANCE_URL")
    if not token:
        missing.append("SALESFORCE_ACCESS_TOKEN")

    if missing:
        raise RuntimeError(f"{', '.join(missing)} environment variable(s) not set")
    return instance_url.rstrip("/"), token


def _headers() -> Dict[str, str]:
    _, token = _get_credentials()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    instance_url, _ = _get_credentials()
    return f"{instance_url}/services/data/{_API_VERSION}"


@tool(credentials=["SALESFORCE_INSTANCE_URL", "SALESFORCE_ACCESS_TOKEN"])
def sf_query(soql: str) -> List[Dict[str, Any]]:
    """Run a SOQL query against Salesforce.

    Args:
        soql: SOQL query string (e.g. ``"SELECT Id, Name FROM Account LIMIT 10"``).

    Returns:
        List of record objects.
    """
    if not soql:
        raise ValueError("soql is required")

    resp = httpx.get(
        f"{_base_url()}/query",
        params={"q": soql},
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return data.get("records", [])


@tool(credentials=["SALESFORCE_INSTANCE_URL", "SALESFORCE_ACCESS_TOKEN"])
def sf_get_record(sobject: str, record_id: str) -> Dict[str, Any]:
    """Get a specific Salesforce record.

    Args:
        sobject: SObject type (e.g. ``"Account"``, ``"Contact"``).
        record_id: The record ID.

    Returns:
        Record object with all fields.
    """
    if not sobject:
        raise ValueError("sobject is required")
    if not record_id:
        raise ValueError("record_id is required")

    resp = httpx.get(
        f"{_base_url()}/sobjects/{sobject}/{record_id}",
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


@tool(credentials=["SALESFORCE_INSTANCE_URL", "SALESFORCE_ACCESS_TOKEN"])
def sf_create_record(sobject: str, fields: Dict[str, Any]) -> Dict[str, str]:
    """Create a new Salesforce record.

    Args:
        sobject: SObject type (e.g. ``"Account"``).
        fields: Dict of field names to values.

    Returns:
        Dict with ``id`` of the created record and ``success`` flag.
    """
    if not sobject:
        raise ValueError("sobject is required")
    if not fields:
        raise ValueError("fields is required")

    resp = httpx.post(
        f"{_base_url()}/sobjects/{sobject}",
        json=fields,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()

    data = resp.json()
    return {"id": data.get("id", ""), "success": str(data.get("success", False))}


@tool(credentials=["SALESFORCE_INSTANCE_URL", "SALESFORCE_ACCESS_TOKEN"])
def sf_update_record(sobject: str, record_id: str, fields: Dict[str, Any]) -> str:
    """Update an existing Salesforce record.

    Args:
        sobject: SObject type (e.g. ``"Account"``).
        record_id: The record ID to update.
        fields: Dict of field names to new values.

    Returns:
        Confirmation message.
    """
    if not sobject:
        raise ValueError("sobject is required")
    if not record_id:
        raise ValueError("record_id is required")
    if not fields:
        raise ValueError("fields is required")

    resp = httpx.patch(
        f"{_base_url()}/sobjects/{sobject}/{record_id}",
        json=fields,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return f"Updated {sobject}/{record_id}"


def get_tools() -> List[Any]:
    """Return all salesforce tools."""
    return [sf_query, sf_get_record, sf_create_record, sf_update_record]
