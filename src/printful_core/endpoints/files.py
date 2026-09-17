"""File library endpoints (v2).

Printful exposes only "add a file" and "get a file by ID". Neither API version
has a list-files endpoint, so any listing must come from a caller's own record.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..request import Request


def add_file(url: str, filename: Optional[str] = None, visible: bool = True) -> Request:
    if not url:
        raise ValueError("A file URL is required.")
    body: Dict[str, Any] = {"url": url, "visible": visible}
    if filename:
        body["filename"] = filename
    return Request("POST", "/files", json=body)


def get_file(file_id: int) -> Request:
    return Request("GET", f"/files/{file_id}")
