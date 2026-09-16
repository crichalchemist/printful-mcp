"""The server's transport lifecycle."""
import pytest

from printful_core import auth
from printful_core.errors import PrintfulAuthError, PrintfulError
from printful_core.request import Request
from printful_mcp import transport as mcp_transport
from printful_mcp.tests.conftest import FakeTransport


def test_one_transport_serves_every_tool(monkeypatch):
    """Two tool calls in one session share a connection pool.

    A transport per call opens a new httpx pool per tool invocation and leaks
    one for the life of the process. This is why the transport is a module
    global rather than built where it is used.
    """
    monkeypatch.setenv("PRINTFUL_API_KEY", "key-for-tests-only")
    monkeypatch.setattr(auth, "load_config", lambda: {})
    monkeypatch.setattr(mcp_transport, "_transport", None)

    first = mcp_transport.get_transport()
    try:
        assert mcp_transport.get_transport() is first
    finally:
        monkeypatch.setattr(mcp_transport, "_transport", None)


def test_missing_credentials_raise_rather_than_build_a_useless_transport(monkeypatch):
    """No token means no transport, and the error says so.

    A transport built with an empty key sends unauthenticated requests and the
    failure surfaces as a 401 from whichever tool the user happened to call
    first, which reads like that tool being broken.
    """
    monkeypatch.delenv("PRINTFUL_API_KEY", raising=False)
    monkeypatch.setattr(auth, "load_config", lambda: {})
    monkeypatch.setattr(mcp_transport, "_transport", None)

    with pytest.raises(PrintfulAuthError):
        mcp_transport.get_transport()


async def test_fake_transport_records_every_request_sent():
    """Every call through `send` is appended to `.sent`.

    Nine downstream tasks assert on `transport.sent` (or `.last`) to check
    which Request a tool built. If `send` stops recording, every one of those
    assertions silently checks an empty or stale list instead of catching a
    wrong endpoint, method, or payload.
    """
    fake = FakeTransport()
    first = Request(method="GET", path="/products/1")
    second = Request(method="GET", path="/products/2")

    await fake.send(first)
    await fake.send(second)

    assert fake.sent == [first, second]


async def test_fake_transport_replays_responses_in_queued_order():
    """Queued responses come back FIFO, in the order they were queued.

    Downstream tool tests that make more than one call (e.g. list-then-detail)
    queue a response per call and assert on each in turn. If the fake replays
    them out of order, the second call's assertion checks the first call's
    canned body, and the failure reads as the tool being wrong rather than the
    fake.
    """
    fake = FakeTransport(responses=[{"data": "first"}, {"data": "second"}])

    first_reply = await fake.send(Request(method="GET", path="/a"))
    second_reply = await fake.send(Request(method="GET", path="/b"))

    assert first_reply == {"data": "first"}
    assert second_reply == {"data": "second"}


async def test_fake_transport_raises_a_queued_exception_instance():
    """A queued exception instance is raised, not returned as a response body.

    This is how downstream tests simulate an API error (e.g. a 404 or a
    validation failure) to assert a tool's `except PrintfulError` path. If
    this stops raising, every such test that expects `pytest.raises(...)`
    fails, and the tool's error-formatting code goes untested.
    """
    error = PrintfulError("not found", status_code=404)
    fake = FakeTransport(responses=[error])

    with pytest.raises(PrintfulError):
        await fake.send(Request(method="GET", path="/missing"))


async def test_fake_transport_refuses_a_queued_exception_class():
    """Queuing the exception class itself is a mistake, and it must fail loudly.

    `isinstance(reply, Exception)` matches instances only. Queuing the class
    (`PrintfulError` instead of `PrintfulError("boom")`) would otherwise make
    the class object come back as the response body — a later-task test then
    fails on some unrelated assertion (e.g. formatting code choking on a class
    instead of a dict) instead of at the point of the actual mistake.
    """
    fake = FakeTransport(responses=[PrintfulError])

    with pytest.raises(TypeError):
        await fake.send(Request(method="GET", path="/missing"))


async def test_fake_transport_defaults_to_empty_data_when_queue_is_exhausted():
    """A call beyond the queued responses gets `{"data": {}}`, not an error.

    Downstream tests that only care about the Request a tool built (not its
    formatted output) rely on this default so they don't have to queue a
    response for every call. If this default changes, tools that read
    `response["data"]` for keys that no longer exist raise a KeyError instead
    of the test's actual assertion running.
    """
    fake = FakeTransport()

    reply = await fake.send(Request(method="GET", path="/anything"))

    assert reply == {"data": {}}


async def test_fake_transport_last_returns_the_most_recent_request():
    """`.last` is the most recently sent Request, not the first.

    Downstream tests that make several calls and only care about checking the
    final one (e.g. after a create-then-fetch flow) use `.last` instead of
    indexing `.sent`. If `.last` returns the wrong end of the list, those
    assertions check the wrong call and a regression in the final request goes
    unnoticed.
    """
    fake = FakeTransport()
    first = Request(method="GET", path="/first")
    second = Request(method="GET", path="/second")

    await fake.send(first)
    await fake.send(second)

    assert fake.last is second
