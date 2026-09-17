"""What `python -m printful_mcp` actually hands the SDK.

This file exists because of a defect no other gate could see. Until mcp 2.x this
module configured the HTTP listener by mutating `mcp.settings.host` and
`mcp.settings.port`. 2.x moved both onto `run()` and left `Settings` without
those fields, so the old form raises `ValueError` -- but only once a user
passes `--transport http`. The module imports clean, the server boots clean,
the whole offline suite passes, and the break waits in a branch nothing runs.

A boot check answers "does it import". These answer "does it dispatch", which
is the question the outage was in. They assert against a fake `run`, so no
socket is ever bound and no port is held.
"""

import sys
from unittest.mock import patch

import pytest

import printful_mcp.__main__ as entrypoint
from printful_mcp.server import mcp


def _dispatch(argv):
    """Run main() with a stubbed run(); return (transport, kwargs) it was given."""
    captured = {}

    def fake_run(transport="stdio", **kwargs):
        captured["transport"] = transport
        captured["kwargs"] = kwargs

    # The key is required by main() before it reaches the dispatch under test.
    # It is never sent anywhere: run() is stubbed and no transport is built.
    with (
        patch.object(sys, "argv", argv),
        patch.object(mcp, "run", fake_run),
        patch.dict("os.environ", {"PRINTFUL_API_KEY": "not-a-real-key"}),
    ):
        entrypoint.main()
    return captured["transport"], captured["kwargs"]


def test_the_default_invocation_is_stdio_with_no_listener():
    """Cursor and Claude Desktop launch the bare module and speak over stdio.

    A host or port leaking into the stdio path would bind a socket for a
    client that never asked for one.
    """
    transport, kwargs = _dispatch(["printful-mcp"])
    assert transport == "stdio"
    assert kwargs == {}


@pytest.mark.parametrize(
    ("flag", "expected_transport"),
    [("http", "streamable-http"), ("sse", "sse")],
)
def test_the_http_transports_receive_host_and_port(flag, expected_transport):
    """The regression that motivated this file.

    `--transport http` must reach run() carrying the address the user asked
    for. Asserting the kwargs rather than the absence of an exception is the
    point: passing host and port to a run() that ignores them would raise
    nothing and listen on the wrong interface.
    """
    transport, kwargs = _dispatch(
        ["printful-mcp", "--transport", flag, "--host", "0.0.0.0", "--port", "9001"]
    )
    assert transport == expected_transport
    assert kwargs == {"host": "0.0.0.0", "port": 9001}


def test_the_user_facing_transport_names_are_not_the_sdk_names():
    """`--transport http` is not a value the SDK accepts.

    The CLI says "http" and the SDK wants "streamable-http". That mapping is
    the whole body of the dispatch, so a rename on either side breaks it
    silently -- argparse rejects an unknown CLI value loudly, but an unknown
    value handed to run() is the SDK's problem, at runtime, on a user's box.
    """
    assert entrypoint.parse_args.__module__ == "printful_mcp.__main__"
    transport, _ = _dispatch(["printful-mcp", "--transport", "http"])
    assert transport == "streamable-http", (
        "the CLI's 'http' must map to the SDK's 'streamable-http'"
    )


def test_a_missing_api_key_exits_rather_than_starting_a_server():
    """Starting without credentials produces a server that fails every call.

    Exiting 1 at launch is what makes the misconfiguration legible in a client's
    logs instead of surfacing as 32 broken tools.
    """
    with (
        patch.object(sys, "argv", ["printful-mcp"]),
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(SystemExit) as exc,
    ):
        entrypoint.main()
    assert exc.value.code == 1
