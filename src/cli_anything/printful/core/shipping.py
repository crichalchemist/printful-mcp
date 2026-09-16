"""Shipping rate, country, and tax operations.

Shipping rates and countries are v2. Tax rate calculation exists only in v1.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..utils.printful_backend import PrintfulBackend

# /v2/countries defaults to 20 rows; request the max per page to keep round trips low.
PAGE_LIMIT = 100


def calculate_rates(
    backend: PrintfulBackend,
    recipient: Dict[str, Any],
    items: List[Dict[str, Any]],
    currency: Optional[str] = None,
    locale: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate live shipping rates.

    Printful notes these are meant to be called immediately before placing an
    order; rates change with live carrier and facility data.
    """
    if not items:
        raise ValueError("Shipping rate calculation requires at least one item.")
    # The endpoint rejects an item without `source` ("must be of type string,
    # null provided"), so default it the way the catalog flow always means it.
    normalized = [
        {**item, "source": item.get("source") or "catalog"} for item in items
    ]
    payload: Dict[str, Any] = {"recipient": recipient, "order_items": normalized}
    if currency:
        payload["currency"] = currency
    if locale:
        payload["locale"] = locale
    return backend.post("/shipping-rates", json_data=payload)


def list_countries(backend: PrintfulBackend, all_pages: bool = True) -> Dict[str, Any]:
    """List shipping countries.

    /v2/countries is paginated and defaults to 20 of ~239 rows, so a single
    request silently omits most countries — including the US. Callers asking
    "does Printful ship to X" need the whole set, so every page is fetched by
    default.
    """
    first = backend.get("/countries", params={"limit": PAGE_LIMIT, "offset": 0})
    if not all_pages:
        return first

    rows = list(first.get("data", []) or [])
    paging = first.get("paging") or {}
    total = paging.get("total")
    limit = paging.get("limit") or PAGE_LIMIT

    if not isinstance(total, int):
        return first

    offset = len(rows)
    while offset < total:
        page = backend.get("/countries", params={"limit": limit, "offset": offset})
        batch = page.get("data", []) or []
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)

    merged = dict(first)
    merged["data"] = rows
    merged["paging"] = {"total": total, "limit": limit, "offset": 0,
                        "returned": len(rows)}
    return merged


def calculate_tax(
    backend: PrintfulBackend,
    country_code: str,
    state_code: Optional[str] = None,
    city: Optional[str] = None,
    zip_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate a tax rate. v1 only — v2 has no tax endpoint."""
    recipient: Dict[str, Any] = {"country_code": country_code}
    if state_code:
        recipient["state_code"] = state_code
    if city:
        recipient["city"] = city
    if zip_code:
        recipient["zip"] = zip_code
    return backend.post("/tax/rates", version="v1", json_data={"recipient": recipient})


def summarize_rates(data: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten shipping rates.

    The live response names the method code `shipping` and its label
    `shipping_method_name` — not `id` and `name`. Reading `id`/`name` yields a
    table of nulls, so both spellings are accepted with the live one first.
    """
    rates = data.get("data", []) or []
    rows = [
        {
            "id": r.get("shipping") or r.get("id"),
            "name": r.get("shipping_method_name") or r.get("name"),
            "rate": r.get("rate"),
            "currency": r.get("currency"),
            "min_days": r.get("min_delivery_days"),
            "max_days": r.get("max_delivery_days"),
            "min_date": r.get("min_delivery_date"),
            "max_date": r.get("max_delivery_date"),
        }
        for r in rates
    ]
    return {"rates": rows, "count": len(rows)}


def summarize_countries(data: Dict[str, Any]) -> Dict[str, Any]:
    countries = data.get("data", []) or []
    rows = [
        {
            "code": c.get("code"),
            "name": c.get("name"),
            "states": len(c.get("states") or []),
        }
        for c in countries
    ]
    return {"countries": rows, "count": len(rows)}
