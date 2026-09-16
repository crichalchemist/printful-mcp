"""The server's transport lifecycle."""
import pytest

from printful_core import auth
from printful_core.errors import PrintfulAuthError
from printful_mcp import transport as mcp_transport


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
