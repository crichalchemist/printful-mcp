"""Order operations (v2).

Read the safety notes before changing anything here: ``confirm_order`` submits an
order for fulfillment and charges the account, and ``cancel_order`` is destructive.
Both are gated behind an explicit --yes at the CLI layer.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from ..utils.printful_backend import PrintfulBackend, PrintfulError

# Commands that cost money or destroy state. The CLI refuses these without --yes.
BILLABLE_OPERATIONS = ("confirm",)
DESTRUCTIVE_OPERATIONS = ("cancel",)


def list_orders(
    backend: PrintfulBackend,
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    return backend.get(
        "/orders", params={"limit": limit, "offset": offset, "status": status}
    )


def get_order(backend: PrintfulBackend, order_id: str) -> Dict[str, Any]:
    return backend.get(f"/orders/{order_id}")


def create_order(backend: PrintfulBackend, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a DRAFT order. Drafts are not charged until confirmed."""
    return backend.post("/orders", json_data=payload)


def update_order(
    backend: PrintfulBackend, order_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    if not payload:
        raise ValueError("Update requires at least one field to change.")
    return backend.patch(f"/orders/{order_id}", json_data=payload)


def cancel_order(backend: PrintfulBackend, order_id: str) -> Dict[str, Any]:
    """Cancel/delete an order. Destructive — requires --yes at the CLI layer."""
    result = backend.delete(f"/orders/{order_id}")
    return result or {"order_id": order_id, "status": "cancelled"}


def confirm_order(backend: PrintfulBackend, order_id: str) -> Dict[str, Any]:
    """Confirm an order for fulfillment.

    THIS CHARGES THE ACCOUNT. The CLI requires an explicit --yes before calling it.
    """
    return backend.post(f"/orders/{order_id}/confirmation")


def list_order_items(backend: PrintfulBackend, order_id: str) -> Dict[str, Any]:
    return backend.get(f"/orders/{order_id}/order-items")


def list_shipments(backend: PrintfulBackend, order_id: str) -> Dict[str, Any]:
    return backend.get(f"/orders/{order_id}/shipments")


def create_estimation_task(
    backend: PrintfulBackend, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Start an async order cost estimation. Free — does not place an order."""
    return backend.post("/order-estimation-tasks", json_data=payload)


def get_estimation_task(backend: PrintfulBackend, task_id: str) -> Dict[str, Any]:
    return backend.get("/order-estimation-tasks", params={"id": task_id})


def estimate_costs(
    backend: PrintfulBackend,
    payload: Dict[str, Any],
    poll: bool = True,
    max_wait: float = 30.0,
    interval: float = 2.0,
) -> Dict[str, Any]:
    """Create an estimation task and poll until it leaves 'pending'.

    Returns the final task body. Raises PrintfulError if the task fails.
    """
    task = create_estimation_task(backend, payload)
    data = task.get("data", task) if isinstance(task, dict) else {}
    task_id = data.get("id")
    if not poll or not task_id:
        return task

    deadline = time.monotonic() + max_wait
    latest = task
    while time.monotonic() < deadline:
        latest = get_estimation_task(backend, task_id)
        body = latest.get("data", latest) if isinstance(latest, dict) else {}
        status = body.get("status")
        if status == "completed":
            return latest
        if status == "failed":
            reasons = body.get("failure_reasons") or []
            raise PrintfulError(
                "Order estimation failed: "
                + ("; ".join(str(r) for r in reasons) or "no reason given"),
                detail=body,
            )
        time.sleep(interval)

    raise PrintfulError(
        f"Order estimation task {task_id} still pending after {max_wait}s. "
        f"Re-check with: orders estimate-status {task_id}",
        detail={"task_id": task_id, "last_response": latest},
    )


def summarize_orders(data: Dict[str, Any]) -> Dict[str, Any]:
    orders = data.get("data", []) or []
    rows = []
    for o in orders:
        costs = o.get("costs") or {}
        rows.append(
            {
                "id": o.get("id"),
                "external_id": o.get("external_id"),
                "status": o.get("status"),
                "created": o.get("created_at"),
                "total": costs.get("total"),
                "currency": costs.get("currency"),
            }
        )
    return {"orders": rows, "paging": data.get("paging", {}), "count": len(rows)}
