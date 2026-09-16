"""Printful API backend — wraps the live Printful REST API (v2 primary, v1 fallback).

This is the harness backend module. The "real software" for this harness is the
hosted Printful API, so every call here goes over HTTPS to api.printful.com. Nothing
is simulated locally.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:
    print(
        "requests library not found. Install with: pip3 install requests",
        file=sys.stderr,
    )
    sys.exit(1)

API_BASE_V2 = os.environ.get("PRINTFUL_API_BASE_V2", "https://api.printful.com/v2").rstrip("/")
API_BASE_V1 = os.environ.get("PRINTFUL_API_BASE_V1", "https://api.printful.com").rstrip("/")

CONFIG_DIR = Path.home() / ".config" / "cli-anything-printful"
CONFIG_FILE = CONFIG_DIR / "config.json"

ENV_API_KEY = "PRINTFUL_API_KEY"
ENV_STORE_ID = "PRINTFUL_STORE_ID"

DEFAULT_TIMEOUT = 30.0

TOKEN_HELP = (
    "Get a token at https://www.printful.com/dashboard/api\n"
    "Then either:\n"
    "  export PRINTFUL_API_KEY=your-token\n"
    "  cli-anything-printful config set api_key your-token"
)


class PrintfulError(Exception):
    """A Printful API error, normalized across v1 and v2 response shapes."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        detail: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.message,
            "status_code": self.status_code,
            "detail": self.detail,
        }


class PrintfulAuthError(PrintfulError):
    """Missing, invalid, or expired credentials."""


class PrintfulRateLimitError(PrintfulError):
    """Rate limited. Carries retry_after seconds when the API supplied it."""

    def __init__(self, message: str, retry_after: Optional[str] = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def get_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_config(config: Dict[str, Any]) -> None:
    get_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


def resolve_api_key(explicit: Optional[str] = None) -> str:
    """Resolve the API token: explicit flag > environment > config file."""
    key = explicit or os.environ.get(ENV_API_KEY) or load_config().get("api_key")
    if not key:
        raise PrintfulAuthError(
            "No Printful API token configured.\n" + TOKEN_HELP, status_code=401
        )
    return key


def resolve_store_id(explicit: Optional[str] = None) -> Optional[str]:
    """Resolve the store ID: explicit flag > environment > config file.

    Only needed for account-level tokens. Store-level tokens already carry their
    store context and must not send the header.
    """
    value = explicit or os.environ.get(ENV_STORE_ID) or load_config().get("store_id")
    return str(value) if value else None


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

class PrintfulBackend:
    """Synchronous client for the Printful API, handling both versions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        store_id: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.api_key = resolve_api_key(api_key)
        self.store_id = resolve_store_id(store_id)
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.store_id:
            headers["X-PF-Store-Id"] = self.store_id
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        endpoint: str,
        version: str = "v2",
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make a request and return the normalized response body.

        v2 bodies are returned as-is. v1 bodies are unwrapped from
        ``{"code": ..., "result": ...}`` down to ``result``.
        """
        base = API_BASE_V2 if version == "v2" else API_BASE_V1
        url = f"{base}{endpoint}"

        # Drop None-valued query params so callers can pass optionals freely.
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=self._headers(extra_headers),
                timeout=self.timeout,
            )
        except requests.Timeout:
            raise PrintfulError(
                f"Request to {url} timed out after {self.timeout}s. Please try again."
            )
        except requests.RequestException as e:
            raise PrintfulError(f"Request error: {e}")

        if response.status_code == 401:
            raise PrintfulAuthError(
                "Unauthorized. The token may be invalid, expired, or missing a "
                "required scope.\nNote: Printful private tokens expire and cannot be "
                "refreshed — they must be regenerated.\n" + TOKEN_HELP,
                status_code=401,
            )

        if response.status_code in (403,):
            raise PrintfulAuthError(
                "Forbidden. The token is valid but lacks the scope for this endpoint. "
                "Check the token's scopes in the Printful dashboard.",
                status_code=403,
            )

        if response.status_code in (429, 419):
            retry_after = response.headers.get("Retry-After", "60")
            raise PrintfulRateLimitError(
                f"Rate limit exceeded. Retry after {retry_after} seconds. "
                "(General limit is 120 requests/60s; mockup creation is far "
                "stricter — 10/60s established stores, 2/60s new stores.)",
                retry_after=retry_after,
                status_code=response.status_code,
            )

        if 200 <= response.status_code < 300:
            if response.status_code == 204 or not response.content:
                return {}
            try:
                data = response.json()
            except ValueError:
                raise PrintfulError(
                    f"Invalid JSON in response from {url} "
                    f"(status {response.status_code})",
                    status_code=response.status_code,
                )
            if version == "v2":
                return data
            return data.get("result", data) if isinstance(data, dict) else data

        self._raise_for_error(response, version, url)

    def _raise_for_error(self, response, version: str, url: str) -> None:
        """Normalize v1 and v2 error bodies into a PrintfulError.

        The v2 docs describe RFC 9457 problem details (`detail`/`title`), but the
        live v2 API actually returns the v1-style envelope for both 4xx and 404:

            {"data": "<message>", "error": {"reason": ..., "message": ...}}

        Verified against live 400 and 404 responses. Reading only `detail`/`title`
        turns every real v2 error into "Unknown error" and hides the cause, so all
        known shapes are tried here regardless of the declared version.
        """
        try:
            body = response.json()
        except ValueError:
            raise PrintfulError(
                f"Request to {url} failed with status {response.status_code}",
                status_code=response.status_code,
            )

        message = self._extract_error_message(body)
        raise PrintfulError(
            message or f"Request to {url} failed with status {response.status_code}",
            status_code=response.status_code,
            detail=body if isinstance(body, dict) else {"body": body},
        )

    @staticmethod
    def _extract_error_message(body: Any) -> Optional[str]:
        """Pull a human-readable message out of any known Printful error shape."""
        if isinstance(body, str):
            return body
        if not isinstance(body, dict):
            return None

        # Shape actually returned by both live v1 and live v2: error.message
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str) and err:
            return err

        # RFC 9457, as the v2 docs describe it.
        for key in ("detail", "title"):
            value = body.get(key)
            if value:
                return str(value)

        # v2 puts the message in `data` alongside `error`; v1 uses `result`.
        for key in ("data", "result", "message"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value

        return None

    # Convenience wrappers -------------------------------------------------

    def get(self, endpoint: str, version: str = "v2", **kwargs) -> Dict[str, Any]:
        return self.request("GET", endpoint, version=version, **kwargs)

    def post(self, endpoint: str, version: str = "v2", **kwargs) -> Dict[str, Any]:
        return self.request("POST", endpoint, version=version, **kwargs)

    def patch(self, endpoint: str, version: str = "v2", **kwargs) -> Dict[str, Any]:
        return self.request("PATCH", endpoint, version=version, **kwargs)

    def delete(self, endpoint: str, version: str = "v2", **kwargs) -> Dict[str, Any]:
        return self.request("DELETE", endpoint, version=version, **kwargs)

    def close(self) -> None:
        self.session.close()
