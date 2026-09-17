"""The fake transport every MCP adapter test uses.

An MCP tool is a thin adapter: validate input, build a Request, send it, format
the reply. The thing worth asserting is which Request came out, so this records
them and replays canned responses rather than simulating the API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from printful_core.request import Request


class FakeTransport:
    """Records every Request sent and returns the next queued response."""

    def __init__(self, responses: Optional[List[Any]] = None):
        self.sent: List[Request] = []
        self._responses = list(responses or [])

    async def send(
        self, request: Request, extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        self.sent.append(request)
        if not self._responses:
            return {"data": {}}
        reply = self._responses.pop(0)
        if isinstance(reply, type) and issubclass(reply, BaseException):
            raise TypeError(
                f"FakeTransport was queued the exception class {reply.__name__}, "
                f"not an instance. Queue {reply.__name__}(...) so it can be "
                "raised, not returned as a response body."
            )
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def last(self) -> Request:
        assert self.sent, "no Request was sent"
        return self.sent[-1]


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()
