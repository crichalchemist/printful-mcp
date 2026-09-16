"""Walk every page of a paginated Printful collection.

/v2/countries defaults to 20 of 239 rows and 'US' is not in the first page
alphabetically, so a single request answers "does Printful ship to the US?"
with no. Pagination belongs here rather than in each endpoint, so the defect
cannot recur one endpoint at a time.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from .request import Request

PAGE_LIMIT = 100


def collect_pages(request: Request,
                  send: Callable[[Request], Dict[str, Any]]) -> Dict[str, Any]:
    """Send `request` and every following page, merging their rows."""
    first = send(request.with_params(limit=PAGE_LIMIT, offset=0))

    rows = list(first.get("data", []) or [])
    paging = first.get("paging") or {}
    total = paging.get("total")
    limit = paging.get("limit") or PAGE_LIMIT

    if not isinstance(total, int):
        return first

    offset = len(rows)
    while offset < total:
        page = send(request.with_params(limit=limit, offset=offset))
        batch = page.get("data", []) or []
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)

    merged = dict(first)
    merged["data"] = rows
    merged["paging"] = {"total": total, "limit": limit, "offset": 0,
                        "returned": len(rows)}
    return merged
