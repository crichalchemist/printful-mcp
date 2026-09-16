"""Mockup generator operations (v2).

Mockup generation is the most tightly rate-limited part of the Printful API:
10 requests/60s for established stores, 2 requests/60s for NEW stores, with a
60-second lockout when exceeded, plus a 20,000 generated-files-per-24h account cap.
The backend surfaces 429 rather than retrying, so callers see the limit instead of
being walked into a lockout.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..utils.printful_backend import PrintfulBackend, PrintfulError

RATE_LIMIT_NOTE = (
    "Mockup creation is rate limited to 10 requests/60s (established stores) or "
    "2 requests/60s (new stores), with a 60s lockout when exceeded."
)


def create_task(
    backend: PrintfulBackend,
    product_id: int,
    variant_ids: List[int],
    image_url: str,
    placement: str = "front",
    technique: str = "dtg",
    mockup_style_ids: Optional[List[int]] = None,
    image_format: str = "jpg",
) -> Dict[str, Any]:
    """Create an async mockup generation task."""
    if not variant_ids:
        raise ValueError("At least one catalog variant ID is required.")
    if not image_url:
        raise ValueError("A design image URL is required.")

    payload: Dict[str, Any] = {
        "format": image_format,
        "products": [
            {
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
        ],
    }
    if mockup_style_ids:
        payload["products"][0]["mockup_style_ids"] = [int(s) for s in mockup_style_ids]
    return backend.post("/mockup-tasks", json_data=payload)


def get_task(backend: PrintfulBackend, task_id: str) -> Dict[str, Any]:
    return backend.get("/mockup-tasks", params={"id": task_id})


def wait_for_task(
    backend: PrintfulBackend,
    task_id: str,
    max_wait: float = 120.0,
    interval: float = 5.0,
) -> Dict[str, Any]:
    """Poll a mockup task until it completes or fails."""
    deadline = time.monotonic() + max_wait
    latest: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = get_task(backend, task_id)
        body = latest.get("data", latest)
        if isinstance(body, list):
            body = body[0] if body else {}
        status = body.get("status")
        if status == "completed":
            return latest
        if status == "failed":
            raise PrintfulError(
                f"Mockup task {task_id} failed: {body.get('reason', 'no reason given')}",
                detail=body,
            )
        time.sleep(interval)
    raise PrintfulError(
        f"Mockup task {task_id} still pending after {max_wait}s. "
        f"Re-check with: mockup status {task_id}",
        detail={"task_id": task_id, "last_response": latest},
    )


def list_styles(backend: PrintfulBackend, product_id: int) -> Dict[str, Any]:
    return backend.get(f"/catalog-products/{product_id}/mockup-styles")


def list_templates(backend: PrintfulBackend, product_id: int) -> Dict[str, Any]:
    return backend.get(f"/catalog-products/{product_id}/mockup-templates")


def extract_mockup_urls(data: Dict[str, Any]) -> List[str]:
    """Pull every mockup image URL out of a completed task response."""
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
                extra_url = extra.get("url")
                if extra_url:
                    urls.append(extra_url)
    return urls
