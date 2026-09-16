"""Guards the safety annotations MCP clients use to gate destructive tools.

`printful_cancel_order` cannot be undone. If its `destructiveHint` were ever
set to False, no other test in this suite would catch it -- the adapter tests
exercise `tools/orders.py` directly and never look at `server.py`'s
`@mcp.tool` annotations. Confirmed by mutation during Task 4: flipping the
hint to False left the full suite green.
"""
from __future__ import annotations

from printful_mcp.server import mcp


async def test_cancel_order_is_flagged_destructive():
    """A client must be able to tell this tool cannot be undone."""
    tools = await mcp.list_tools()
    cancel = next(t for t in tools if t.name == "printful_cancel_order")
    assert cancel.annotations.destructiveHint is True
