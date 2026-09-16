"""Printful error types and envelope normalization.

The v2 documentation describes RFC 9457 problem details, but the live API
returns the v1-style envelope for both 4xx and 404:

    {"data": "<message>", "error": {"reason": "...", "message": "..."}}

Reading only detail/title reduces every real error to "Unknown error" and hides
its cause, so every known shape is tried here regardless of API version.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

TOKEN_HELP = (
    "Get a token at https://www.printful.com/dashboard/api\n"
    "Then either:\n"
    "  export PRINTFUL_API_KEY=your-token\n"
    "  printful config set api_key your-token"
)

RATE_LIMIT_HELP = (
    "The general limit is 120 requests/60s. Mockup creation is far stricter: "
    "10/60s for established stores and 2/60s for new stores, with a 60s lockout."
)


class PrintfulError(Exception):
    """A Printful API error, normalized across every envelope shape."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        detail: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {"error": self.message, "status_code": self.status_code, "detail": self.detail}


class PrintfulAuthError(PrintfulError):
    """Missing, invalid, expired, or under-scoped credentials."""


class PrintfulRateLimitError(PrintfulError):
    """Rate limited. Carries Retry-After when the API supplied it."""

    def __init__(self, message: str, retry_after: Optional[str] = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


def extract_message(body: Any) -> Optional[str]:
    """Pull a human-readable message out of any known Printful error shape."""
    if isinstance(body, str):
        return body or None
    if not isinstance(body, dict):
        return None

    error = body.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    if isinstance(error, str) and error:
        return error

    for key in ("detail", "title", "data", "result", "message"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def raise_for_status(
    status: int, body: Any, url: str, headers: Optional[Mapping[str, str]] = None
) -> None:
    """Raise the appropriate PrintfulError for a non-2xx response."""
    headers = headers or {}

    if status == 401:
        raise PrintfulAuthError(
            "Unauthorized. The token may be invalid, expired, or missing a "
            "required scope.\nPrintful private tokens expire and cannot be "
            "refreshed — they must be regenerated.\n" + TOKEN_HELP,
            status_code=401,
        )

    if status == 403:
        raise PrintfulAuthError(
            "Forbidden. The token is valid but lacks the scope for this "
            "endpoint. Check its scopes in the Printful dashboard.",
            status_code=403,
        )

    if status in (429, 419):
        retry_after = headers.get("Retry-After", "60")
        raise PrintfulRateLimitError(
            f"Rate limit exceeded. Retry after {retry_after} seconds. " + RATE_LIMIT_HELP,
            retry_after=retry_after,
            status_code=status,
        )

    message = extract_message(body)
    raise PrintfulError(
        message or f"Request to {url} failed with status {status}",
        status_code=status,
        detail=body if isinstance(body, dict) else {"body": body},
    )
