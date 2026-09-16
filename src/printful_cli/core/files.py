"""File library operations for the CLI.

Printful exposes only "add a file" and "get a file by ID" — there is no list-files
endpoint in either API version. `list_added` reads the session's local record
instead, which is the only way to recall IDs added through this CLI.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from printful_core.endpoints import files as endpoints
from printful_core.transport import SyncTransport


def add_file(transport: SyncTransport, url: str, filename: Optional[str] = None,
             visible: bool = True) -> Dict[str, Any]:
    return transport.send(endpoints.add_file(url, filename, visible))


def get_file(transport: SyncTransport, file_id: int) -> Dict[str, Any]:
    return transport.send(endpoints.get_file(file_id))


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
