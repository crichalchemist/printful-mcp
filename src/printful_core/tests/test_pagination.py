from printful_core.pagination import PAGE_LIMIT, collect_pages
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
