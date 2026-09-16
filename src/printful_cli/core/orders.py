"""Order operations for the CLI.

confirm_order charges the account and cancel_order is destructive. Both are
gated behind --yes in the command layer, not here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from printful_core import polling
from printful_core.endpoints import orders as endpoints
from printful_core.format import summary
from printful_core.transport import SyncTransport


def list_orders(
    transport: SyncTransport, limit: int = 20, offset: int = 0, status: Optional[str] = None
) -> Dict[str, Any]:
    return summary.orders(transport.send(endpoints.list_orders(limit, offset, status)))


def get_order(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    return transport.send(endpoints.get_order(order_id))


def create_order(
    transport: SyncTransport,
    recipient: Dict[str, Any],
    items: List[Dict[str, Any]],
    external_id: Optional[str] = None,
    shipping: Optional[str] = None,
) -> Dict[str, Any]:
    return transport.send(endpoints.create_order(recipient, items, external_id, shipping))


def update_order(
    transport: SyncTransport, order_id: str, changes: Dict[str, Any]
) -> Dict[str, Any]:
    return transport.send(endpoints.update_order(order_id, changes))


def cancel_order(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    result = transport.send(endpoints.cancel_order(order_id))
    return result or {"order_id": order_id, "status": "cancelled"}


def confirm_order(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    """CHARGES THE ACCOUNT. The command layer requires --yes first."""
    return transport.send(endpoints.confirm_order(order_id))


def list_items(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    return transport.send(endpoints.list_items(order_id))


def list_shipments(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    return transport.send(endpoints.list_shipments(order_id))


def estimate_costs(
    transport: SyncTransport,
    recipient: Dict[str, Any],
    items: List[Dict[str, Any]],
    poll: bool = True,
    max_wait: float = 30.0,
    interval: float = 2.0,
) -> Dict[str, Any]:
    """Create an estimation task and poll until it leaves 'pending'."""
    task = transport.send(endpoints.create_estimation_task(recipient, items))
    task_id = polling.task_body(task).get("id")
    if not poll or not task_id:
        return task

    return polling.poll_estimation_task(
        endpoints.get_estimation_task(task_id), transport.send, task_id, task, max_wait, interval
    )
