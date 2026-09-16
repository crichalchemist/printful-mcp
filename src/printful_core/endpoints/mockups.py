"""Mockup generator endpoints (v2).

Mockup creation is the most tightly limited part of the API: 10 requests/60s
for established stores, 2/60s for new stores, a 60-second lockout on exceeding
it, and 20,000 generated files per account per 24 hours.
"""

from __future__ import annotations

from typing import List, Optional

from ..request import Request

RATE_LIMIT_NOTE = (
    "Mockup creation is limited to 10 requests/60s (established stores) or "
    "2 requests/60s (new stores), with a 60s lockout when exceeded."
)


def create_task(
    product_id: int,
    variant_ids: List[int],
    image_url: str,
    placement: str = "front",
    technique: str = "dtg",
    style_ids: Optional[List[int]] = None,
    image_format: str = "jpg",
) -> Request:
    if not variant_ids:
        raise ValueError("At least one catalog variant ID is required.")
    if not image_url:
        raise ValueError("A design image URL is required.")

    product = {
        "source": "catalog",
        "catalog_product_id": int(product_id),
        "catalog_variant_ids": [int(v) for v in variant_ids],
        "orientation": "any",
        "placements": [
            {
                "placement": placement,
                "technique": technique,
                "layers": [{"type": "file", "url": image_url}],
            }
        ],
    }
    if style_ids:
        product["mockup_style_ids"] = [int(s) for s in style_ids]

    return Request("POST", "/mockup-tasks", json={"format": image_format, "products": [product]})


def get_task(task_id: str) -> Request:
    return Request("GET", "/mockup-tasks", params={"id": task_id})


def list_styles(product_id: int) -> Request:
    return Request("GET", f"/catalog-products/{product_id}/mockup-styles")


def list_templates(product_id: int) -> Request:
    return Request("GET", f"/catalog-products/{product_id}/mockup-templates")
