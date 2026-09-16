"""Flatten API responses into table-friendly rows.

Field names come from live responses, not the documentation. Shipping rates in
particular are keyed `shipping` and `shipping_method_name`; reading `id` and
`name` yields a table of nulls.
"""
from __future__ import annotations

from typing import Any, Dict, List


def products(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    for product in data.get("data", []) or []:
        techniques = product.get("techniques") or []
        rows.append({
            "id": product.get("id"),
            "name": product.get("name"),
            "type": product.get("type"),
            "brand": product.get("brand"),
            "variants": product.get("variant_count"),
            "techniques": ",".join(t.get("key", "") for t in techniques
                                   if isinstance(t, dict)),
        })
    return {"products": rows, "paging": data.get("paging", {}), "count": len(rows)}


def variants(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{
        "id": v.get("id"), "name": v.get("name"),
        "size": v.get("size"), "color": v.get("color"),
    } for v in data.get("data", []) or []]
    return {"variants": rows, "paging": data.get("paging", {}), "count": len(rows)}


def orders(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    for order in data.get("data", []) or []:
        costs = order.get("costs") or {}
        rows.append({
            "id": order.get("id"),
            "external_id": order.get("external_id"),
            "status": order.get("status"),
            "created": order.get("created_at"),
            "total": costs.get("total"),
            "currency": costs.get("currency"),
        })
    return {"orders": rows, "paging": data.get("paging", {}), "count": len(rows)}


def rates(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{
        "id": r.get("shipping") or r.get("id"),
        "name": r.get("shipping_method_name") or r.get("name"),
        "rate": r.get("rate"),
        "currency": r.get("currency"),
        "min_days": r.get("min_delivery_days"),
        "max_days": r.get("max_delivery_days"),
        "min_date": r.get("min_delivery_date"),
        "max_date": r.get("max_delivery_date"),
    } for r in data.get("data", []) or []]
    return {"rates": rows, "count": len(rows)}


def countries(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{
        "code": c.get("code"), "name": c.get("name"),
        "states": len(c.get("states") or []),
    } for c in data.get("data", []) or []]
    return {"countries": rows, "count": len(rows)}


def stores(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{
        "id": s.get("id"), "name": s.get("name"),
        "type": s.get("type"), "website": s.get("website"),
    } for s in data.get("data", []) or []]
    return {"stores": rows, "count": len(rows)}


def mockup_urls(data: Dict[str, Any]) -> List[str]:
    """Every mockup image URL in a completed task response."""
    body = data.get("data", data)
    if isinstance(body, dict):
        body = [body]

    urls: List[str] = []
    for task in body or []:
        if not isinstance(task, dict):
            continue
        for item in task.get("mockups", []) or []:
            url = item.get("mockup_url") or item.get("url")
            if url:
                urls.append(url)
            for extra in item.get("extra", []) or []:
                if extra.get("url"):
                    urls.append(extra["url"])
    return urls
