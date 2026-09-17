"""Credential resolution and request headers.

X-PF-Store-Id is sent only when a store is configured. Account-level tokens
require it on every store-scoped endpoint; store-level tokens carry their own
context and must not send it.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import TOKEN_HELP, PrintfulAuthError

CONFIG_DIR = Path.home() / ".config" / "printful"
CONFIG_FILE = CONFIG_DIR / "config.json"

ENV_API_KEY = "PRINTFUL_API_KEY"
ENV_STORE_ID = "PRINTFUL_STORE_ID"


def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, IOError):
        return {}


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as handle:
        json.dump(config, handle, indent=2)
    with contextlib.suppress(OSError):
        os.chmod(CONFIG_FILE, 0o600)


@dataclass(frozen=True)
class Credentials:
    api_key: str
    store_id: Optional[str] = None

    @classmethod
    def resolve(
        cls, api_key: Optional[str] = None, store_id: Optional[Any] = None
    ) -> "Credentials":
        """Resolve credentials: explicit argument, then environment, then config."""
        config = load_config()

        key = api_key or os.environ.get(ENV_API_KEY) or config.get("api_key")
        if not key:
            raise PrintfulAuthError(
                "No Printful API token configured.\n" + TOKEN_HELP, status_code=401
            )

        store = store_id or os.environ.get(ENV_STORE_ID) or config.get("store_id")
        return cls(api_key=key, store_id=str(store) if store else None)

    def headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.store_id:
            headers["X-PF-Store-Id"] = self.store_id
        if extra:
            headers.update(extra)
        return headers
