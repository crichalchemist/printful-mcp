"""Poll a Printful async task until it leaves 'pending'.

Printful runs cost estimation and mockup generation as tasks: the create call
returns an id, and the caller re-reads it until the status settles. Both loops
lived in the CLI, which meant the MCP server had to grow its own copies.

Body extraction and status classification are the decisions both tasks share,
so they live here as pure functions. Everything else differs — the two task
kinds report failure under different keys and say different things on timeout —
so each keeps its own driver rather than being forced through one parameterized
message builder. The drivers own the deadline, the sleep and the strings; they
contain no branching logic of their own.

What a driver will not say is what the caller should do next. Recovery advice
names a command, and the CLI's commands are not the MCP server's, so a caller
that has one passes it in.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict

from .errors import PrintfulError
from .request import Request


def task_body(response: Any) -> Dict[str, Any]:
    """The task itself, unwrapped from whatever envelope carried it.

    Printful returns a task as `{"data": {...}}`, as `{"data": [{...}]}`, or
    bare. Callers get the same treatment for all three so one task kind is not
    left unable to read a shape the other handles.
    """
    if not isinstance(response, dict):
        return {}
    body = response.get("data", response)
    if isinstance(body, list):
        body = body[0] if body else {}
    return body


def classify_task(body: Dict[str, Any]) -> str:
    """'completed', 'failed', or 'pending' — anything unrecognized is pending."""
    status = body.get("status")
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    return "pending"


def _estimation_failure(body: Dict[str, Any]) -> PrintfulError:
    reasons = body.get("failure_reasons") or []
    return PrintfulError(
        "Order estimation failed: "
        + ("; ".join(str(r) for r in reasons) or "no reason given"),
        detail=body)


def _estimation_timeout(task_id: str, max_wait: float,
                        latest: Dict[str, Any]) -> PrintfulError:
    return PrintfulError(
        f"Order estimation task {task_id} still pending after {max_wait}s.",
        detail={"task_id": task_id, "last_response": latest})


def poll_estimation_task(request: Request,
                         send: Callable[[Request], Dict[str, Any]],
                         task_id: str, created: Dict[str, Any],
                         max_wait: float, interval: float) -> Dict[str, Any]:
    """Re-send `request` until the estimation task settles.

    `created` is the response that opened the task; it is what the timeout
    reports when the deadline has already passed before the first re-read.
    """
    deadline = time.monotonic() + max_wait
    latest = created
    while time.monotonic() < deadline:
        latest = send(request)
        body = task_body(latest)
        status = classify_task(body)
        if status == "completed":
            return latest
        if status == "failed":
            raise _estimation_failure(body)
        time.sleep(interval)
    raise _estimation_timeout(task_id, max_wait, latest)


async def poll_estimation_task_async(
        request: Request,
        send: Callable[[Request], Awaitable[Dict[str, Any]]],
        task_id: str, created: Dict[str, Any],
        max_wait: float, interval: float) -> Dict[str, Any]:
    """`poll_estimation_task` over an awaitable sender."""
    deadline = time.monotonic() + max_wait
    latest = created
    while time.monotonic() < deadline:
        latest = await send(request)
        body = task_body(latest)
        status = classify_task(body)
        if status == "completed":
            return latest
        if status == "failed":
            raise _estimation_failure(body)
        await asyncio.sleep(interval)
    raise _estimation_timeout(task_id, max_wait, latest)


def _mockup_failure(task_id: str, body: Dict[str, Any]) -> PrintfulError:
    return PrintfulError(
        f"Mockup task {task_id} failed: {body.get('reason', 'no reason given')}",
        detail=body,
    )


def _mockup_timeout(task_id: str, max_wait: float, latest: Dict[str, Any],
                    recovery_hint: str) -> PrintfulError:
    """A timeout, plus whatever the caller tells its own users to do next.

    A mockup task outlives the call that was watching it, so the message is
    only useful if it says how to pick the task back up. How to do that is the
    caller's to say -- the CLI names a shell command, and an MCP client has no
    shell to run one in -- so the core states the timeout and stops there.
    """
    message = f"Mockup task {task_id} still pending after {max_wait}s."
    if recovery_hint:
        message = f"{message} {recovery_hint}"
    return PrintfulError(
        message,
        detail={"task_id": task_id, "last_response": latest},
    )


def poll_mockup_task(request: Request,
                     send: Callable[[Request], Dict[str, Any]],
                     task_id: str, max_wait: float, interval: float,
                     recovery_hint: str = "") -> Dict[str, Any]:
    """Re-send `request` until the mockup task completes or fails.

    `recovery_hint` is appended to the timeout message after a single space.
    """
    deadline = time.monotonic() + max_wait
    latest: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = send(request)
        body = task_body(latest)
        status = classify_task(body)
        if status == "completed":
            return latest
        if status == "failed":
            raise _mockup_failure(task_id, body)
        time.sleep(interval)
    raise _mockup_timeout(task_id, max_wait, latest, recovery_hint)


async def poll_mockup_task_async(
        request: Request,
        send: Callable[[Request], Awaitable[Dict[str, Any]]],
        task_id: str, max_wait: float, interval: float,
        recovery_hint: str = "") -> Dict[str, Any]:
    """`poll_mockup_task` over an awaitable sender."""
    deadline = time.monotonic() + max_wait
    latest: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = await send(request)
        body = task_body(latest)
        status = classify_task(body)
        if status == "completed":
            return latest
        if status == "failed":
            raise _mockup_failure(task_id, body)
        await asyncio.sleep(interval)
    raise _mockup_timeout(task_id, max_wait, latest, recovery_hint)
