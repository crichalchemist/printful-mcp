"""Mockup generator operations for the CLI.

Mockup generation is the most tightly rate-limited part of the Printful API:
10 requests/60s for established stores, 2 requests/60s for NEW stores, with a
60-second lockout when exceeded, plus a 20,000 generated-files-per-24h account cap.
The transport surfaces 429 rather than retrying, so callers see the limit instead
of being walked into a lockout.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from printful_core import polling
from printful_core.endpoints import mockups as endpoints
from printful_core.format import summary
from printful_core.transport import SyncTransport

# Re-exported so the command layer keeps one name for one implementation.
RATE_LIMIT_NOTE = endpoints.RATE_LIMIT_NOTE
extract_mockup_urls = summary.mockup_urls


def create_task(transport: SyncTransport, product_id: int,
                variant_ids: List[int], image_url: str,
                placement: str = "front", technique: str = "dtg",
                mockup_style_ids: Optional[List[int]] = None,
                image_format: str = "jpg") -> Dict[str, Any]:
    """Create an async mockup generation task."""
    return transport.send(endpoints.create_task(
        product_id, variant_ids, image_url, placement, technique,
        mockup_style_ids, image_format))


def get_task(transport: SyncTransport, task_id: str) -> Dict[str, Any]:
    return transport.send(endpoints.get_task(task_id))


def wait_for_task(transport: SyncTransport, task_id: str,
                  max_wait: float = 120.0,
                  interval: float = 5.0) -> Dict[str, Any]:
    """Poll a mockup task until it completes or fails."""
    return polling.poll_mockup_task(
        endpoints.get_task(task_id), transport.send, task_id,
        max_wait, interval,
        recovery_hint=f"Re-check with: mockup status {task_id}")


def list_styles(transport: SyncTransport, product_id: int) -> Dict[str, Any]:
    return transport.send(endpoints.list_styles(product_id))


def list_templates(transport: SyncTransport, product_id: int) -> Dict[str, Any]:
    """Mockup templates for one product — note the required product_id.

    printful_core.endpoints.stores.list_templates shares this name but takes
    (limit, offset), so passing a product ID there binds it silently to limit.
    """
    return transport.send(endpoints.list_templates(product_id))
