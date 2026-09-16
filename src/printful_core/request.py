"""The request description shared by every Printful surface.

A Request says what to send without sending it. Building one performs no I/O,
so endpoint paths and payload shapes can be asserted without a network call —
and the same description serves a synchronous CLI and an asynchronous server.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Request:
    """An un-sent Printful API call."""

    method: str
    path: str
    version: str = "v2"
    params: Dict[str, Any] = field(default_factory=dict)
    json: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        # Callers pass optional filters straight through; dropping None here
        # keeps every endpoint builder free of the same three-line dance.
        cleaned = {k: v for k, v in (self.params or {}).items() if v is not None}
        object.__setattr__(self, "params", cleaned)
        # A frozen Request that aliases the caller's body is not frozen in the
        # way callers read it: mutating that dict afterwards changes what gets
        # sent. Copy it here so no builder has to remember to.
        if self.json is not None:
            object.__setattr__(self, "json", dict(self.json))

    def with_params(self, **extra: Any) -> "Request":
        """Return a copy with additional query parameters."""
        merged = {**self.params, **extra}
        return replace(self, params=merged)
