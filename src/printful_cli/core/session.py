"""Session state for printful_cli.

There is no Printful project file, so the persistent state this harness carries is
the draft order under construction, the selected store, the file IDs added during
the session, and the command history.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_SESSION_FILE = str(Path.home() / ".cli-anything-printful" / "session.json")
MAX_HISTORY = 50


def _locked_save_json(path: str, data: Any, **dump_kwargs) -> None:
    """Atomically write JSON with an exclusive file lock."""
    try:
        f = open(path, "r+")
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f = open(path, "w")
    with f:
        locked = False
        try:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            locked = True
        except (ImportError, OSError):
            pass
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, **dump_kwargs)
            f.flush()
        finally:
            if locked:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class DraftOrder:
    """An order being assembled across multiple commands."""

    RECIPIENT_FIELDS = (
        "name",
        "address1",
        "address2",
        "city",
        "state_code",
        "country_code",
        "zip",
        "email",
        "phone",
    )

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        data = data or {}
        self.recipient: Dict[str, Any] = data.get("recipient", {})
        self.items: List[Dict[str, Any]] = data.get("items", [])
        self.external_id: Optional[str] = data.get("external_id")
        self.shipping: Optional[str] = data.get("shipping")

    def set_recipient(self, **fields) -> Dict[str, Any]:
        """Set recipient fields. Unknown keys are rejected loudly."""
        unknown = [k for k in fields if k not in self.RECIPIENT_FIELDS]
        if unknown:
            raise ValueError(
                f"Unknown recipient field(s): {', '.join(sorted(unknown))}. "
                f"Valid fields: {', '.join(self.RECIPIENT_FIELDS)}"
            )
        for key, value in fields.items():
            if value is not None:
                self.recipient[key] = value
        return self.recipient

    def add_item(
        self,
        catalog_variant_id: int,
        quantity: int = 1,
        placement: Optional[str] = None,
        image_url: Optional[str] = None,
        technique: Optional[str] = None,
        external_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if quantity < 1:
            raise ValueError(f"quantity must be >= 1, got {quantity}")
        item: Dict[str, Any] = {
            "source": "catalog",
            "catalog_variant_id": int(catalog_variant_id),
            "quantity": int(quantity),
        }
        if external_id:
            item["external_id"] = external_id
        if image_url:
            placements = {
                "placement": placement or "front",
                "technique": technique or "dtg",
                "layers": [{"type": "file", "url": image_url}],
            }
            item["placements"] = [placements]
        self.items.append(item)
        return item

    def remove_item(self, index: int) -> Dict[str, Any]:
        if not self.items:
            raise ValueError("Draft has no items to remove.")
        if index < 0 or index >= len(self.items):
            raise ValueError(
                f"Item index {index} out of range (draft has {len(self.items)} "
                f"item(s), valid indices 0-{len(self.items) - 1})."
            )
        return self.items.pop(index)

    def clear(self) -> None:
        self.recipient = {}
        self.items = []
        self.external_id = None
        self.shipping = None

    def missing_fields(self) -> List[str]:
        """Required pieces still absent before the draft can be submitted.

        Note the asymmetry: shipping rates can be calculated for an item with no
        artwork, but creating the order cannot — Printful rejects a catalog order
        item without `placements` ("Property `placements` is required"), because
        it has nothing to print. Items missing a design are reported here so
        `draft show` warns before submission rather than failing at the API.
        """
        missing = []
        required_recipient = ("name", "address1", "city", "country_code", "zip")
        for field in required_recipient:
            if not self.recipient.get(field):
                missing.append(f"recipient.{field}")
        # Printful requires a state code for these countries.
        if self.recipient.get("country_code") in ("US", "CA", "AU") and not self.recipient.get(
            "state_code"
        ):
            missing.append("recipient.state_code")
        if not self.items:
            missing.append("items (at least one)")
        for index, item in enumerate(self.items):
            if item.get("source", "catalog") == "catalog" and not item.get("placements"):
                missing.append(
                    f"items[{index}].placements — variant "
                    f"{item.get('catalog_variant_id')} has no design; add one with "
                    f"`draft add-item --variant-id {item.get('catalog_variant_id')} "
                    f"--image-url <url>`"
                )
        return missing

    def priceable(self) -> bool:
        """True when the draft can be rate-quoted, even without artwork."""
        return bool(self.items and self.recipient.get("country_code"))

    def is_complete(self) -> bool:
        return not self.missing_fields()

    def to_api_payload(self) -> Dict[str, Any]:
        """Build the POST /v2/orders request body."""
        missing = self.missing_fields()
        if missing:
            raise ValueError(
                "Draft order is incomplete. Missing: " + ", ".join(missing)
            )
        payload: Dict[str, Any] = {
            "recipient": dict(self.recipient),
            "order_items": list(self.items),
        }
        if self.external_id:
            payload["external_id"] = self.external_id
        if self.shipping:
            payload["shipping"] = self.shipping
        return payload

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipient": self.recipient,
            "items": self.items,
            "external_id": self.external_id,
            "shipping": self.shipping,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "recipient_set": bool(self.recipient),
            "recipient_name": self.recipient.get("name"),
            "destination": self.recipient.get("country_code"),
            "item_count": len(self.items),
            "total_quantity": sum(i.get("quantity", 0) for i in self.items),
            "items_without_design": sum(
                1 for i in self.items
                if i.get("source", "catalog") == "catalog" and not i.get("placements")
            ),
            "priceable": self.priceable(),
            "complete": self.is_complete(),
            "missing": self.missing_fields(),
        }


class PrintfulSession:
    """Persistent CLI session: draft order, store context, files, history."""

    def __init__(self, session_file: Optional[str] = None):
        self.session_file = session_file or DEFAULT_SESSION_FILE
        self.draft = DraftOrder()
        self.store_id: Optional[str] = None
        self.files: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self._modified = False
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.session_file):
            return
        try:
            with open(self.session_file, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return
        self.draft = DraftOrder(data.get("draft", {}))
        self.store_id = data.get("store_id")
        self.files = data.get("files", [])
        self.history = data.get("history", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft": self.draft.to_dict(),
            "store_id": self.store_id,
            "files": self.files,
            "history": self.history,
        }

    def save_session(self) -> None:
        _locked_save_json(self.session_file, self.to_dict(), indent=2)
        self._modified = False

    def touch(self) -> None:
        """Mark session state as modified so auto-save picks it up."""
        self._modified = True

    def set_store(self, store_id: Optional[str]) -> None:
        self.store_id = str(store_id) if store_id else None
        self.touch()

    def record_file(self, file_id: Any, url: str = "", filename: str = "") -> Dict[str, Any]:
        """Record a file added through this CLI.

        Printful has no list-files endpoint in either API version, so this local
        record is the only way to recall file IDs added during a session.
        """
        record = {
            "id": file_id,
            "url": url,
            "filename": filename,
            "added_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.files.append(record)
        self.touch()
        return record

    def save_history(self, command: str, result: Optional[Dict[str, Any]] = None) -> None:
        self.history.append(
            {
                "command": command,
                "result": result or {},
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
        )
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]
        self.touch()

    def clear(self) -> None:
        self.draft.clear()
        self.files = []
        self.history = []
        self.touch()

    def status(self) -> Dict[str, Any]:
        return {
            "session_file": self.session_file,
            "store_id": self.store_id,
            "draft": self.draft.summary(),
            "file_count": len(self.files),
            "history_count": len(self.history),
            "modified": self._modified,
        }
