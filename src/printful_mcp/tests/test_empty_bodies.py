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
