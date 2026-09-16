"""Every registered tool survives a success that carries no body.

`printful_core.transport._normalize` returns `{}` for a 204 and for any 2xx
whose body is empty. A renderer that reads a response key by subscript then
raises `KeyError` *inside the tool's own `try`*, where `except PrintfulError`
and `except ValueError` do not catch it, and the MCP client gets a traceback
instead of a string. `printful_confirm_order` does this after the account has
already been charged: the caller is billed and handed the traceback.

This is parametrized over the registrations read out of `server.py` rather than
a hand-written list, the way `test_server.py` reads them, so a tool added later
is covered without anyone having to remember this file. A tool whose input
model cannot be built from `_SAMPLES` fails loudly naming itself rather than
disappearing from the run.
"""

from typing import Any, Dict, Optional

import pytest

from printful_core.request import Request
from printful_mcp.tests.toolsamples import REGISTERED, SKIP, sample_input, tool_function


class _EmptyBodyTransport:
    """Answers every request with `{}`, as a 204 or empty 2xx does.

    Not `conftest.FakeTransport`: that one falls back to `{"data": {}}` once its
    queue runs dry, which is the shape this test exists to avoid, and a tool may
    send more than one request (`list_countries` walks pages).
    """

    def __init__(self) -> None:
        self.sent = []

    async def send(
        self, request: Request, extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        self.sent.append(request)
        return {}


def test_the_registration_scan_found_the_whole_surface():
    """A scan that silently matched nothing would make every case below vacuous."""
    assert len(REGISTERED) >= 30, (
        f"read only {len(REGISTERED)} registrations out of server.py: {sorted(REGISTERED)}"
    )


@pytest.mark.parametrize("tool_name", sorted(REGISTERED))
async def test_an_empty_success_body_is_reported_not_raised(tool_name):
    """A 2xx with no body means the operation worked. Say so, do not raise.

    An error return would be a second wrong answer -- the order really was
    confirmed. The renderers degrade to 'unknown'/'N/A' instead.
    """
    if tool_name in SKIP:
        pytest.skip(SKIP[tool_name])

    func = tool_function(tool_name)
    transport = _EmptyBodyTransport()

    args = [transport]
    params = sample_input(tool_name)
    if params is not None:
        args.append(params)

    try:
        result = await func(*args)
    except Exception as exc:  # noqa: BLE001 - must catch any escape to report it via pytest.fail
        pytest.fail(f"{tool_name} raised {type(exc).__name__}: {exc} on an empty 2xx body")

    assert isinstance(result, str), f"{tool_name} returned {type(result).__name__}, not str"
    assert transport.sent, (
        f"{tool_name} returned before sending anything, so nothing rendered the "
        "empty body. Fix this test's sample input, not the tool."
    )
    assert result.strip(), (
        f"{tool_name} returned an empty string for an empty body. A caller cannot "
        "tell that apart from a tool that did nothing."
    )

    # Deliberately NOT asserted: that `result` looks like a rendered document --
    # a "#" heading, an "Error:" or a "✓". Three tools legitimately return none
    # of those, and a prefix list widened until they pass asserts nothing:
    #
    #   printful_create_mockup_task     -> "{}"
    #   printful_get_mockup_task        -> "No task found with ID 1"
    #   printful_create_estimation_task -> "Estimation task created.\n\nTask ID: None..."
    #
    # The first two short-circuit on `if not body:` and never reach a renderer,
    # so this file structurally cannot exercise the reads in tools/mockups.py --
    # test_mockups.py covers those with a non-empty body missing its keys, which
    # is the shape that actually breaks them. The third does read the body; it
    # renders prose rather than a heading, which is a fact about the assertion's
    # shape, not a gap in the tool.
