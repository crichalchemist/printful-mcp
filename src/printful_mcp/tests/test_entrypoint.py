"""What `python -m printful_mcp` actually hands the SDK, on either SDK major.

This file exists because of a defect no other gate could see. mcp 1.x configures
the HTTP listener through `mcp.settings.host` / `.port`; 2.x removed those fields
and takes them as `run()` keywords, and each SDK rejects the other's form -- 2.x
raises `ValueError` on the assignment, 1.x raises `TypeError` on the keyword,
because its `run()` has no `**kwargs`.

Either way the break is reachable only once a user passes `--transport http`.
The module imports clean, the server boots clean, and the whole offline suite
passes. A boot check answers "does it import"; these answer "does it dispatch",
which is the question the outage is in.

**These assert the outcome, not the mechanism.** Which of the two paths carries
the address is exactly what differs between SDK majors, so a test that pinned
the mechanism would have to be rewritten on every upgrade -- and would pass for
the wrong reason on the leg it was not written for. `_address_given_to_sdk`
reads whichever path the running SDK uses and the assertions compare addresses.

They run against a stubbed `run()`, so no socket is bound and no port held.
"""

import sys
from unittest.mock import patch

import pytest

import printful_mcp.__main__ as entrypoint
from printful_mcp.server import mcp

# True on mcp 1.x, False on 2.x. Named once here so a failure message can say
# which leg produced it -- otherwise a red CI matrix cell is ambiguous.
SETTINGS_CARRY_THE_ADDRESS = hasattr(mcp.settings, "host")
SDK_LEG = "mcp 1.x (settings)" if SETTINGS_CARRY_THE_ADDRESS else "mcp 2.x (run kwargs)"


def _dispatch(argv):
    """Run main() with a stubbed run(). Returns what the SDK was handed."""
    captured = {}

    def fake_run(transport="stdio", **kwargs):
        captured["transport"] = transport
        captured["kwargs"] = kwargs
        # Snapshot inside the call: on mcp 1.x the address is already on
        # settings by now, and the fixture restores them afterwards.
        captured["settings"] = (
            getattr(mcp.settings, "host", None),
            getattr(mcp.settings, "port", None),
        )

    before = (getattr(mcp.settings, "host", None), getattr(mcp.settings, "port", None))
    try:
        # The key is required by main() before it reaches the dispatch under
        # test. It is never sent anywhere: run() is stubbed, no transport built.
        with (
            patch.object(sys, "argv", argv),
            patch.object(mcp, "run", fake_run),
            patch.dict("os.environ", {"PRINTFUL_API_KEY": "not-a-real-key"}),
        ):
            entrypoint.main()
    finally:
        # main() mutates a module global on the 1.x leg. Put it back, or the
        # next test inherits an address it never set.
        if SETTINGS_CARRY_THE_ADDRESS:
            mcp.settings.host, mcp.settings.port = before
    return captured


def _address_given_to_sdk(captured):
    """The (host, port) the SDK received, by whichever route this SDK uses."""
    if captured["kwargs"]:
        return captured["kwargs"].get("host"), captured["kwargs"].get("port")
    return captured["settings"]


def test_the_default_invocation_is_stdio_with_no_listener():
    """Cursor and Claude Desktop launch the bare module and speak over stdio.

    A host or port leaking into the stdio path would bind a socket for a client
    that never asked for one.
    """
    captured = _dispatch(["printful-mcp"])
    assert captured["transport"] == "stdio"
    assert captured["kwargs"] == {}


@pytest.mark.parametrize(
    ("flag", "expected_transport"),
    [("http", "streamable-http"), ("sse", "sse")],
)
def test_the_http_transports_receive_host_and_port(flag, expected_transport):
    """The regression that motivated this file.

    `--transport http` must reach the SDK carrying the address the user asked
    for. Asserting the address rather than the absence of an exception is the
    point: handing host and port to a path the SDK ignores raises nothing and
    listens on the wrong interface.
    """
    captured = _dispatch(
        ["printful-mcp", "--transport", flag, "--host", "0.0.0.0", "--port", "9001"]
    )
    assert captured["transport"] == expected_transport
    assert _address_given_to_sdk(captured) == ("0.0.0.0", 9001), (
        f"address did not reach the SDK on this leg -- {SDK_LEG}"
    )


def test_the_compat_branch_takes_the_route_this_sdk_actually_offers():
    """Guards the failure mode dual support introduces.

    A compat branch is only as good as the leg CI runs, and the tempting bug is
    a branch that silently takes the wrong route and still passes because the
    other route happens to be harmless. This pins the correspondence directly:
    on an SDK whose settings carry the address, run() must get no address
    keywords, and vice versa.
    """
    captured = _dispatch(
        ["printful-mcp", "--transport", "http", "--host", "10.0.0.1", "--port", "9100"]
    )
    if SETTINGS_CARRY_THE_ADDRESS:
        assert captured["kwargs"] == {}, (
            "mcp 1.x run() has no **kwargs -- passing host/port there is a TypeError"
        )
        assert captured["settings"] == ("10.0.0.1", 9100)
    else:
        assert captured["kwargs"] == {"host": "10.0.0.1", "port": 9100}
        assert captured["settings"] == (None, None), (
            "mcp 2.x Settings has no host/port field; writing one raises ValueError"
        )


def test_the_user_facing_transport_names_are_not_the_sdk_names():
    """`--transport http` is not a value the SDK accepts.

    The CLI says "http" and the SDK wants "streamable-http". That mapping is the
    whole body of the dispatch, so a rename on either side breaks it silently --
    argparse rejects an unknown CLI value loudly, but an unknown value handed to
    run() is the SDK's problem, at runtime, on a user's box.
    """
    captured = _dispatch(["printful-mcp", "--transport", "http"])
    assert captured["transport"] == "streamable-http", (
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
