"""Walk every page of a paginated Printful collection.

/v2/countries defaults to 20 of 239 rows and 'US' is not in the first page
alphabetically, so a single request answers "does Printful ship to the US?"
with no. Pagination belongs here rather than in each endpoint, so the defect
cannot recur one endpoint at a time.

Every decision lives in a pure function that neither sleeps nor sends, so the
synchronous CLI and the asynchronous MCP server share the arithmetic rather
than each owning a copy of it. The two drivers below are loops and nothing else.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from .request import Request

PAGE_LIMIT = 100


def _rows(page: Dict[str, Any]) -> List[Any]:
    return list(page.get("data", []) or [])


def first_page_request(request: Request) -> Request:
    """The opening call: ask for the largest page the API will give."""
    return request.with_params(limit=PAGE_LIMIT, offset=0)


def next_page_request(request: Request,
                      pages_so_far: Sequence[Dict[str, Any]]) -> Optional[Request]:
    """The call that follows `pages_so_far`, or None when the walk is done.

    Offset advances by the rows actually accumulated, never by the requested
    limit: a server that returns fewer rows than asked for would otherwise skip
    the difference. A non-integer `total` means the collection is not paginated
    in the shape we understand, so the walk stops after one page.
    """
    first = pages_so_far[0]
    paging = first.get("paging") or {}
    total = paging.get("total")
    if not isinstance(total, int):
        return None

    # A page that came back empty means the server has no more rows to give,
    # whatever `total` claims. Without this the walk cannot terminate.
    if len(pages_so_far) > 1 and not _rows(pages_so_far[-1]):
        return None

    offset = sum(len(_rows(page)) for page in pages_so_far)
    if offset >= total:
        return None

    limit = paging.get("limit") or PAGE_LIMIT
    return request.with_params(limit=limit, offset=offset)


def merge_pages(pages: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Concatenate the rows of every page into one first-page-shaped body."""
    first = pages[0]
    paging = first.get("paging") or {}
    total = paging.get("total")
    if not isinstance(total, int):
        return first

    rows = [row for page in pages for row in _rows(page)]
    limit = paging.get("limit") or PAGE_LIMIT
    merged = dict(first)
    merged["data"] = rows
    merged["paging"] = {"total": total, "limit": limit, "offset": 0,
                        "returned": len(rows)}
    return merged


def collect_pages(request: Request,
                  send: Callable[[Request], Dict[str, Any]]) -> Dict[str, Any]:
    """Send `request` and every following page, merging their rows."""
    pages = [send(first_page_request(request))]
    while True:
        following = next_page_request(request, pages)
        if following is None:
            return merge_pages(pages)
        pages.append(send(following))


async def collect_pages_async(
        request: Request,
        send: Callable[[Request], Awaitable[Dict[str, Any]]]) -> Dict[str, Any]:
    """`collect_pages` over an awaitable sender. Used by the MCP server."""
    pages = [await send(first_page_request(request))]
    while True:
        following = next_page_request(request, pages)
        if following is None:
            return merge_pages(pages)
        pages.append(await send(following))
