"""Google Analytics tools — GA Data API v1 integration."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from agentspan.agents import tool


def _get_credentials() -> tuple[str, str]:
    token = os.environ.get("GA_ACCESS_TOKEN", "")
    property_id = os.environ.get("GA_PROPERTY_ID", "")

    missing = []
    if not token:
        missing.append("GA_ACCESS_TOKEN")
    if not property_id:
        missing.append("GA_PROPERTY_ID")

    if missing:
        raise RuntimeError(f"{', '.join(missing)} environment variable(s) not set")
    return token, property_id


def _headers() -> Dict[str, str]:
    token, _ = _get_credentials()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _property_id() -> str:
    _, prop_id = _get_credentials()
    return prop_id


@tool(credentials=["GA_ACCESS_TOKEN", "GA_PROPERTY_ID"])
def ga_run_report(
    metrics: List[str],
    dimensions: Optional[List[str]] = None,
    date_range: str = "7daysAgo",
) -> Dict[str, Any]:
    """Run a Google Analytics report.

    Args:
        metrics: List of metric names (e.g. ``["activeUsers", "sessions"]``).
        dimensions: Optional list of dimension names (e.g. ``["date", "country"]``).
        date_range: Start date or relative date (default ``"7daysAgo"``).

    Returns:
        Report data with ``rows``, ``metricHeaders``, ``dimensionHeaders``.
    """
    if not metrics:
        raise ValueError("metrics is required and must be non-empty")

    prop_id = _property_id()

    payload: Dict[str, Any] = {
        "dateRanges": [{"startDate": date_range, "endDate": "today"}],
        "metrics": [{"name": m} for m in metrics],
    }
    if dimensions:
        payload["dimensions"] = [{"name": d} for d in dimensions]

    resp = httpx.post(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{prop_id}:runReport",
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


@tool(credentials=["GA_ACCESS_TOKEN", "GA_PROPERTY_ID"])
def ga_get_realtime() -> Dict[str, Any]:
    """Get realtime active users from Google Analytics.

    Returns:
        Realtime report with active users count.
    """
    prop_id = _property_id()

    payload = {
        "metrics": [{"name": "activeUsers"}],
    }

    resp = httpx.post(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{prop_id}:runRealtimeReport",
        json=payload,
        headers=_headers(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def get_tools() -> List[Any]:
    """Return all google_analytics tools."""
    return [ga_run_report, ga_get_realtime]
