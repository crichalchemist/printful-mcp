"""A minimal valid input for every registered tool, built from `server.py`.

Two tests need the same two things: the list of tools the server actually
registers, and an input model instance that will carry a call all the way to
its renderer. Neither is cheap to get right -- the registrations are read out
of the source because a delegate's body is the only place the implementation
it calls is written down, and a "minimal" input has to satisfy the core's own
validation, not just Pydantic's, or the tool returns an error string without
ever sending and the test that asked for it passes while exercising nothing.

Parametrizing over `REGISTERED` rather than a hand-written list is what keeps a
tool added later covered without anyone having to remember these files.
"""

import ast
import importlib
import pathlib
from typing import Dict, Optional, get_args, get_type_hints

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


def tool_function(tool_name: str):
    """The `tools/<domain>.py` callable that `tool_name`'s delegate calls."""
    module_name, func_name = REGISTERED[tool_name]
    return getattr(importlib.import_module(f"printful_mcp.tools.{module_name}"), func_name)


def sample_input(tool_name: str, fmt: Optional[str] = None):
    """A minimal valid input for `tool_name`, or `None` if there is none to build.

    `None` means the caller should pass no `params` at all: the tool takes no
    arguments (`printful_list_countries`), or -- when `fmt` is given -- its
    model has no output-format field to set. `CreateMockupTaskInput.format`
    is `Literal["jpg", "png"]`, an *image* format, so it fails that check and
    is excluded by the property rather than by name.

    `fmt` is needed because `_minimal_params` fills only required fields and
    `format` carries a default: without it a caller asking for json would
    silently exercise the markdown path.
    """
    model = get_type_hints(tool_function(tool_name)).get("params")
    if model is None:
        return None
    if fmt is not None:
        field = model.model_fields.get("format")
        if field is None or set(get_args(field.annotation)) != {"markdown", "json"}:
            return None
    params = _minimal_params(model, tool_name)
    if fmt is not None:
        params = params.model_copy(update={"format": fmt})
    return params
