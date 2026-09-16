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

import ast
import importlib
import pathlib
from typing import Any, Dict, Optional, get_type_hints

import pytest

from printful_core.request import Request

_SRC = pathlib.Path(__file__).resolve().parents[2]

# printful_mcp.tools mirrors printful_core.endpoints module-for-module; the same
# set names both. `test_server.py` reads server.py against this set too.
_TOOL_MODULES = {"catalog", "files", "mockups", "orders", "shipping", "stores", "sync"}

# Tools this test cannot construct an input for. Every entry needs a reason.
# Empty today: every registered tool's required fields are covered by _SAMPLES
# or by _BY_TYPE. A tool must not be added here to quiet a real crash.
SKIP: Dict[str, str] = {}

# Required-field values chosen so the call reaches the renderer. A value that
# only satisfies Pydantic is not enough: a tool that rejects its own input
# returns an error string without ever sending, which would pass this test
# while exercising nothing. `items_json` therefore carries the placements the
# core's `_require_placements` demands.
_SAMPLES = {
    "items_json": (
        '[{"source": "catalog", "catalog_variant_id": 4012, "quantity": 1, '
        '"placements": [{"placement": "front", "technique": "dtg", "layers": '
        '[{"type": "file", "url": "https://example.com/art.png"}]}]}]'
    ),
    "changes_json": '{"recipient": {"address1": "2 New Street"}}',
    "variant_ids": "4012",
    "design_url": "https://example.com/art.png",
    "url": "https://example.com/art.png",
    "date_from": "2026-01-01",
    "date_to": "2026-06-01",
}

# Anything else required: a value of the right type. What it says does not
# matter here -- the response is empty whatever was asked for.
_BY_TYPE = {int: 1, str: "1", bool: True, float: 1.0}


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


def _registrations() -> Dict[str, tuple]:
    """Registered tool name -> (tools module, function), read from server.py.

    `mcp.list_tools()` returns the names but cannot see which implementation a
    delegate body calls, and importing a delegate to call it would resolve
    credentials. `test_server.py` reads the same source for the same reason.
    """
    src = (_SRC / "printful_mcp" / "server.py").read_text()
    found = {}
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        name = None
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    name = kw.value.value
        if name is None:
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            fn = call.func
            if (
                isinstance(fn, ast.Attribute)
                and isinstance(fn.value, ast.Name)
                and fn.value.id in _TOOL_MODULES
            ):
                found[name] = (fn.value.id, fn.attr)
    return found


REGISTERED = _registrations()


def _minimal_params(model, tool_name: str):
    """The smallest valid input for `model`, or a failure naming the gap."""
    values = {}
    for field_name, field in model.model_fields.items():
        if not field.is_required():
            continue
        if field_name in _SAMPLES:
            values[field_name] = _SAMPLES[field_name]
            continue
        sample = _BY_TYPE.get(field.annotation)
        assert sample is not None, (
            f"{tool_name}: no sample value for required field {field_name}: "
            f"{field.annotation}. Add one to _SAMPLES -- do not add the tool to SKIP."
        )
        values[field_name] = sample
    return model(**values)


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

    module_name, func_name = REGISTERED[tool_name]
    func = getattr(importlib.import_module(f"printful_mcp.tools.{module_name}"), func_name)
    transport = _EmptyBodyTransport()

    args = [transport]
    hints = get_type_hints(func)
    if "params" in hints:
        args.append(_minimal_params(hints["params"], tool_name))

    try:
        result = await func(*args)
    except Exception as exc:  # noqa: BLE001 - must catch any escape to report it via pytest.fail
        pytest.fail(f"{tool_name} raised {type(exc).__name__}: {exc} on an empty 2xx body")

    assert isinstance(result, str), f"{tool_name} returned {type(result).__name__}, not str"
    assert transport.sent, (
        f"{tool_name} returned before sending anything, so nothing rendered the "
        "empty body. Fix this test's sample input, not the tool."
    )
