"""Shipping operations for the CLI."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from printful_core.endpoints import shipping as endpoints
from printful_core.format import summary
from printful_core.pagination import collect_pages
from printful_core.transport import SyncTransport


def list_countries(transport: SyncTransport) -> Dict[str, Any]:
    """Every page. A single request omits the US."""
    response = collect_pages(endpoints.list_countries(), transport.send)
    return summary.countries(response)


def calculate_rates(
    transport: SyncTransport,
    recipient: Dict[str, Any],
    items: List[Dict[str, Any]],
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    response = transport.send(endpoints.calculate_rates(recipient, items, currency))
    return summary.rates(response)


def calculate_tax(
    transport: SyncTransport,
    country_code: str,
    state_code: Optional[str] = None,
    city: Optional[str] = None,
    zip_code: Optional[str] = None,
) -> Dict[str, Any]:
    return transport.send(endpoints.calculate_tax(country_code, state_code, city, zip_code))
