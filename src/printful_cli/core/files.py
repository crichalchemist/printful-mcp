"""File library operations (v2).

Printful exposes only "add a file" and "get a file by ID" — there is no list-files
endpoint in either API version. `list_added` reads the session's local record
instead, which is the only way to recall IDs added through this CLI.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..utils.printful_backend import PrintfulBackend


def add_file(
    backend: PrintfulBackend,
    url: str,
    filename: Optional[str] = None,
    visible: bool = True,
) -> Dict[str, Any]:
    if not url:
        raise ValueError("A file URL is required.")
    payload: Dict[str, Any] = {"url": url, "visible": visible}
    if filename:
        payload["filename"] = filename
    return backend.post("/files", json_data=payload)


def get_file(backend: PrintfulBackend, file_id: int) -> Dict[str, Any]:
    return backend.get(f"/files/{file_id}")


def list_added(session_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """List files added via this CLI in the current session.

    This is a local record, NOT a server query — the Printful API has no
    list-files endpoint.
    """
    return {
        "files": list(session_files),
        "count": len(session_files),
        "source": "session-local",
        "note": (
            "Printful has no list-files endpoint; these are files added through "
            "this CLI and recorded in the session."
        ),
    }
