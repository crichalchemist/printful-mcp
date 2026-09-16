"""The server's registration surface.

These are the tests that make the parity claim checkable. The spec's prose and
table disagreed with each other and with the code about how many operations
this plan added. Rather than pick a number, this asserts the property the
number was trying to express: every endpoint the core can build, the server
can reach, through exactly one registered tool.

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
# printful_mcp.tools mirrors printful_core.endpoints module-for-module by
# convention, so the same set names both; kept as a separate name because
# _delegate_targets and _builders_bound_by_tools read different trees.
TOOL_MODULES = ENDPOINT_MODULES


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


def _tool_functions() -> set:
    """Every public async function in printful_mcp.tools -- the implementations."""
    root = _SRC / "printful_mcp" / "tools"
    found = set()
    for path in sorted(root.glob("*.py")):
        if path.stem == "__init__":
            continue
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_"):
                found.add(f"{path.stem}.{node.name}")
    return found


def _delegate_targets() -> set:
    """Every `<tools module>.<function>(` call made from a server.py delegate.

    server.py is the only place a registered tool NAME is tied to an
    implementation, and `list_tools()` cannot see a function body. Read the
    source for the same reason the endpoint tests do: importing to inspect
    would resolve credentials.
    """
    src = (_SRC / "printful_mcp" / "server.py").read_text()
    found = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute)
                and isinstance(fn.value, ast.Name)
                and fn.value.id in TOOL_MODULES):
            found.add(f"{fn.value.id}.{fn.attr}")
    return found


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


def test_every_tool_function_is_reachable_through_exactly_one_delegate():
    """A delegate pointing at the wrong function orphans the right one.

    The two set tests above read `tools/` and cannot see `server.py`; the
    count test reads `list_tools()` and cannot see a function body. Between
    them a delegate can call the wrong implementation, leaving one tool
    function unreachable and the count unchanged, which is a wrong answer
    with no failing test. Comparing the two sets names the orphan.
    """
    implemented = _tool_functions()
    delegated = _delegate_targets()
    assert implemented - delegated == set(), (
        f"no delegate calls these tool functions: {sorted(implemented - delegated)}")
    assert delegated - implemented == set(), (
        f"server.py delegates to functions that do not exist: "
        f"{sorted(delegated - implemented)}")


def _registered_tool_names() -> list:
    """Every name passed to an @mcp.tool decorator, in source order.

    Duplicates are invisible at runtime: FastMCP keeps the first registration
    under a repeated name and rejects the second with a printed warning, not
    an exception, so `list_tools()` silently returns one tool where two were
    written. Only the source shows both.
    """
    src = (_SRC / "printful_mcp" / "server.py").read_text()
    names = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    names.append(kw.value.value)
    return names


def test_no_tool_name_is_registered_twice():
    """A repeated name loses a tool with no error anywhere.

    Nine tasks appended registrations to one file. FastMCP keeps the first
    registration under a duplicate name and prints a warning for the second
    rather than raising, so the *later* tool simply stops existing -- and a
    runtime check cannot see it, because the rejected registration never
    reaches `list_tools()`.
    """
    names = _registered_tool_names()
    duplicated = sorted({n for n in names if names.count(n) > 1})
    assert not duplicated, f"registered more than once in server.py: {duplicated}"


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
