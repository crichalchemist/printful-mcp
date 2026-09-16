"""The server's transport: one AsyncTransport, created on first use.

This is deliberately not a FastMCP lifespan handler. A lifespan handler was
tried here and failed, and the commits that reached this lazy-global design
exist for that reason -- see `CLAUDE.md` in the repository root. Do not reintroduce one.
"""
from __future__ import annotations

import asyncio
import atexit
from typing import Optional

from printful_core.auth import Credentials
from printful_core.transport import AsyncTransport

_transport: Optional[AsyncTransport] = None


def _close_transport() -> None:
    """Close the transport at interpreter exit."""
    global _transport
    if _transport is None:
        return
    try:
        asyncio.run(_transport.close())
    except RuntimeError:
        # At shutdown there may be no usable event loop. The process is going
        # away and the socket goes with it, so this is one of the few places
        # where swallowing is the honest answer rather than hiding a failure.
        pass
    finally:
        _transport = None


def get_transport() -> AsyncTransport:
    """The server's transport, created on first use."""
    global _transport
    if _transport is None:
        _transport = AsyncTransport(Credentials.resolve())
        atexit.register(_close_transport)
    return _transport
