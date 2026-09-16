from printful_core.pagination import (
    PAGE_LIMIT,
    collect_pages,
    collect_pages_async,
    first_page_request,
    merge_pages,
    next_page_request,
)
from printful_core.request import Request


def make_sender(pages):
    sent = []

    def send(request):
        sent.append(request)
        return pages.pop(0)

    send.sent = sent
    return send


def test_walks_every_page():
    send = make_sender([
        {"data": [{"code": "AF"}, {"code": "AL"}],
         "paging": {"total": 5, "limit": 2, "offset": 0}},
        {"data": [{"code": "DE"}, {"code": "GB"}],
         "paging": {"total": 5, "limit": 2, "offset": 2}},
        {"data": [{"code": "US"}],
         "paging": {"total": 5, "limit": 2, "offset": 4}},
    ])
    result = collect_pages(Request("GET", "/countries"), send)
    assert [row["code"] for row in result["data"]] == ["AF", "AL", "DE", "GB", "US"]
    assert result["paging"]["returned"] == 5
    assert len(send.sent) == 3


def test_offset_advances_on_each_request():
    send = make_sender([
        {"data": [1, 2], "paging": {"total": 4, "limit": 2, "offset": 0}},
        {"data": [3, 4], "paging": {"total": 4, "limit": 2, "offset": 2}},
    ])
    collect_pages(Request("GET", "/countries"), send)
    assert send.sent[1].params["offset"] == 2


def test_first_request_uses_page_limit():
    send = make_sender([{"data": [], "paging": {"total": 0, "limit": 100, "offset": 0}}])
    collect_pages(Request("GET", "/countries"), send)
    assert send.sent[0].params["limit"] == PAGE_LIMIT


def test_missing_paging_returns_first_page():
    send = make_sender([{"data": [{"code": "US"}]}])
    assert len(collect_pages(Request("GET", "/countries"), send)["data"]) == 1


def test_empty_page_stops_the_loop():
    send = make_sender([
        {"data": [{"code": "AF"}], "paging": {"total": 99, "limit": 1, "offset": 0}},
        {"data": [], "paging": {"total": 99, "limit": 1, "offset": 1}},
    ])
    assert len(collect_pages(Request("GET", "/countries"), send)["data"]) == 1


def test_single_page_needs_one_request():
    send = make_sender([{"data": [1], "paging": {"total": 1, "limit": 100, "offset": 0}}])
    collect_pages(Request("GET", "/countries"), send)
    assert len(send.sent) == 1


def test_server_limit_propagates_to_later_requests():
    """A server that caps the page size smaller than PAGE_LIMIT keeps that cap."""
    send = make_sender([
        {"data": [1, 2], "paging": {"total": 4, "limit": 2, "offset": 0}},
        {"data": [3, 4], "paging": {"total": 4, "limit": 2, "offset": 2}},
    ])
    collect_pages(Request("GET", "/countries"), send)
    assert send.sent[0].params["limit"] == PAGE_LIMIT   # first page asks for the max
    assert send.sent[1].params["limit"] == 2            # later pages honor the server's cap


# --------------------------------------------------------------------------
# The pure decisions, exercised with no transport at all
# --------------------------------------------------------------------------

def test_first_page_request_asks_for_the_maximum():
    opening = first_page_request(Request("GET", "/countries"))
    assert opening.params == {"limit": PAGE_LIMIT, "offset": 0}


def test_first_page_request_keeps_the_callers_own_params():
    opening = first_page_request(Request("GET", "/countries", params={"q": "x"}))
    assert opening.params["q"] == "x"


def test_next_page_offsets_by_rows_received_not_by_limit_asked_for():
    """A short page must not make the walk skip the rows it did not receive."""
    pages = [{"data": [1, 2], "paging": {"total": 10, "limit": 100, "offset": 0}}]
    assert next_page_request(Request("GET", "/countries"), pages).params["offset"] == 2


def test_next_page_stops_once_every_row_is_accounted_for():
    pages = [{"data": [1, 2], "paging": {"total": 2, "limit": 100, "offset": 0}}]
    assert next_page_request(Request("GET", "/countries"), pages) is None


def test_next_page_stops_on_a_non_integer_total():
    pages = [{"data": [1], "paging": {"total": None, "limit": 100}}]
    assert next_page_request(Request("GET", "/countries"), pages) is None


def test_next_page_stops_when_the_server_runs_dry_early():
    """`total` can overstate what the server will actually hand over."""
    pages = [{"data": [1], "paging": {"total": 99, "limit": 1, "offset": 0}},
             {"data": [], "paging": {"total": 99, "limit": 1, "offset": 1}}]
    assert next_page_request(Request("GET", "/countries"), pages) is None


def test_merge_pages_concatenates_in_order_and_recounts():
    merged = merge_pages([
        {"data": ["AF"], "paging": {"total": 3, "limit": 1, "offset": 0}},
        {"data": ["GB"], "paging": {"total": 3, "limit": 1, "offset": 1}},
        {"data": ["US"], "paging": {"total": 3, "limit": 1, "offset": 2}},
    ])
    assert merged["data"] == ["AF", "GB", "US"]
    assert merged["paging"] == {"total": 3, "limit": 1, "offset": 0, "returned": 3}


def test_merge_pages_hands_back_an_unpaginated_body_untouched():
    body = {"data": [{"code": "US"}]}
    assert merge_pages([body]) is body


# --------------------------------------------------------------------------
# The sync and async drivers must not be able to disagree
# --------------------------------------------------------------------------

def make_async_sender(pages):
    sent = []

    async def send(request):
        sent.append(request)
        return pages.pop(0)

    send.sent = sent
    return send


def _page_fixture():
    return [
        {"data": [{"code": "AF"}, {"code": "AL"}],
         "paging": {"total": 5, "limit": 2, "offset": 0}},
        {"data": [{"code": "DE"}, {"code": "GB"}],
         "paging": {"total": 5, "limit": 2, "offset": 2}},
        {"data": [{"code": "US"}],
         "paging": {"total": 5, "limit": 2, "offset": 4}},
    ]


def _calls(send):
    return [(r.params["limit"], r.params["offset"]) for r in send.sent]


async def test_both_drivers_walk_the_same_pages_identically():
    """If the MCP server's walk can diverge from the CLI's, sharing bought nothing."""
    sync_send = make_sender(_page_fixture())
    async_send = make_async_sender(_page_fixture())

    from_sync = collect_pages(Request("GET", "/countries"), sync_send)
    from_async = await collect_pages_async(Request("GET", "/countries"), async_send)

    assert from_sync == from_async
    assert _calls(sync_send) == _calls(async_send)
    assert _calls(async_send) == [(PAGE_LIMIT, 0), (2, 2), (2, 4)]


async def test_both_drivers_stop_on_the_same_empty_page():
    fixture = lambda: [
        {"data": [{"code": "AF"}], "paging": {"total": 99, "limit": 1, "offset": 0}},
        {"data": [], "paging": {"total": 99, "limit": 1, "offset": 1}},
    ]
    sync_send = make_sender(fixture())
    async_send = make_async_sender(fixture())

    from_sync = collect_pages(Request("GET", "/countries"), sync_send)
    from_async = await collect_pages_async(Request("GET", "/countries"), async_send)

    assert from_sync == from_async
    assert _calls(sync_send) == _calls(async_send) == [(PAGE_LIMIT, 0), (1, 1)]


async def test_both_drivers_return_an_unpaginated_body_after_one_call():
    sync_send = make_sender([{"data": [{"code": "US"}]}])
    async_send = make_async_sender([{"data": [{"code": "US"}]}])

    from_sync = collect_pages(Request("GET", "/countries"), sync_send)
    from_async = await collect_pages_async(Request("GET", "/countries"), async_send)

    assert from_sync == from_async == {"data": [{"code": "US"}]}
    assert _calls(sync_send) == _calls(async_send) == [(PAGE_LIMIT, 0)]
