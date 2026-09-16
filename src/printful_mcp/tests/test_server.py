"""The server's registration surface.

These are the tests that make the parity claim checkable. The spec's prose said
"fourteen operations" and its table said twelve; the code says thirteen. Rather
than pick a number, this asserts the property the number was trying to express:
every endpoint the core can build, the server can reach.

`tool.annotations` is a `ToolAnnotations` object with attribute access, and
`mcp.list_tools()` is a coroutine returning `list[Tool]`. Both were confirmed
against the installed `mcp` version.
"""
import ast
import pathlib

import pytest

from printful_mcp.server import mcp

_SRC = pathlib.Path(__file__).resolve().parents[2]

# Core endpoints deliberately not bound to a tool. Every entry needs a reason.
# Empty today: `files list` is CLI session state with no endpoint behind it, so
# it never appears in this set -- there is no builder for it to exclude.
UNBOUND_ON_PURPOSE: dict[str, str] = {}

ENDPOINT_MODULES = {"catalog", "files", "mockups", "orders", "shipping", "stores", "sync"}


def _core_request_builders() -> set:
    """Every public `-> Request` function in printful_core.endpoints."""
    root = _SRC / "printful_core" / "endpoints"
    found = set()
    for path in sorted(root.glob("*.py")):
        if path.stem == "__init__":
            continue
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
                continue
            if node.returns is not None and ast.unparse(node.returns) == "Request":
                found.add(f"{path.stem}.{node.name}")
    return found


def _builders_bound_by_tools() -> set:
    """Every `<endpoint module>.<name>(` call made from printful_mcp.tools."""
    root = _SRC / "printful_mcp" / "tools"
    bound = set()
    for path in sorted(root.glob("*.py")):
        if path.stem == "__init__":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if (isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id in ENDPOINT_MODULES):
                bound.add(f"{fn.value.id}.{fn.attr}")
    return bound


async def _tools():
    return await mcp.list_tools()


def test_every_core_endpoint_is_bound_by_a_tool():
    """Name the endpoints no tool calls -- do not just count them.

    Comparing two lengths passes when one builder is unbound and some other
    builder is bound twice, which is exactly the state a half-finished domain
    task leaves behind. This compares the sets, so the failure message names
    the endpoint that has no caller.
    """
    missing = _core_request_builders() - _builders_bound_by_tools()
    missing -= set(UNBOUND_ON_PURPOSE)
    assert missing == set(), (
        f"no tool calls these core endpoints: {sorted(missing)}. "
        "Bind each one, or add it to UNBOUND_ON_PURPOSE with a reason."
    )


def test_no_tool_calls_an_endpoint_that_does_not_exist():
    """A typo'd builder name fails at runtime, inside a try/except, as a string.

    `catalog.get_categories` (plural) would be an AttributeError swallowed by
    nothing -- it raises before the request is built and surfaces as a tool
    that always errors. This catches it without running the tool.
    """
    unknown = _builders_bound_by_tools() - _core_request_builders()
    # `build_catalog_item` is a payload helper, not an endpoint; tools may call it.
    unknown -= {"orders.build_catalog_item"}
    assert unknown == set(), f"tools call endpoints the core does not define: {sorted(unknown)}"


async def test_one_registered_tool_per_bound_endpoint():
    """A tool body with no @mcp.tool registration is unreachable.

    The set tests above read the tool modules, which cannot see whether
    server.py registered anything. This is the half that can.
    """
    expected = len(_core_request_builders()) - len(UNBOUND_ON_PURPOSE)
    names = [tool.name for tool in await _tools()]
    assert len(names) == expected, (
        f"{expected} endpoints bound, {len(names)} tools registered: {sorted(names)}"
    )


async def test_no_tool_name_is_registered_twice():
    """FastMCP silently keeps the last registration under a duplicate name.

    Eight tasks appended registrations to one file; a copy-paste that reuses a
    name loses a tool with no error anywhere.
    """
    names = [tool.name for tool in await _tools()]
    assert len(names) == len(set(names))


async def test_every_tool_is_namespaced():
    assert all(tool.name.startswith("printful_") for tool in await _tools())


@pytest.mark.parametrize("required", [
    "title", "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint",
])
async def test_every_tool_declares_the_full_annotation_set(required):
    """An MCP client reads these to decide whether to ask a human first.

    A missing destructiveHint on printful_cancel_order means a client may run
    it without confirming. That is a safety defect, not a documentation one.
    """
    for tool in await _tools():
        assert tool.annotations is not None, f"{tool.name} has no annotations"
        value = getattr(tool.annotations, required, None)
        assert value is not None, f"{tool.name} is missing {required}"


async def test_the_tools_that_spend_money_are_marked_destructive():
    """Two tools are irreversible and one of them charges the account.

    printful_confirm_order starts fulfillment and bills the card.
    printful_cancel_order cannot be undone. An MCP client decides whether to
    prompt a human from these fields alone.
    """
    by_name = {tool.name: tool for tool in await _tools()}
    for name in ("printful_confirm_order", "printful_cancel_order"):
        assert by_name[name].annotations.destructiveHint is True, \
            f"{name} is destructive and must say so"
        assert by_name[name].annotations.readOnlyHint is False
