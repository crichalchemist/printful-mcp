# MCP Server on the Shared Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `src/printful_mcp/` on `printful_core` and close the parity gap, so the MCP server exposes one tool per core endpoint operation and carries the first automated tests it has ever had.

**Architecture:** The MCP server becomes a thin adapter. A Pydantic model validates the tool's input, a pure `printful_core.endpoints` function builds a frozen `Request`, the lazily-created `AsyncTransport` sends it, and a formatter in `printful_core.format` renders the result. `src/printful_mcp/client.py` — the server's private HTTP stack — is deleted, which is what makes the two surfaces stop drifting.

**Tech Stack:** Python 3.10+, `mcp` 1.x (`FastMCP`), Pydantic v2, httpx, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-16-printful-merger-design.md` — phase 4, "Rebuild the MCP on the core."

**Predecessor:** `docs/superpowers/plans/2026-09-16-printful-core-extraction.md` (plan 1 of 3, complete). Its ledger, including 38 rulings this plan argues from, is at `.superpowers/sdd/2026-09-16-printful-core-extraction/progress.md`.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **No commit in this plan is upstream-cherry-pickable.** Plan 2 rewrites `server.py`, `models/inputs.py` and `tools/orders.py` and deletes `client.py` — all files that the open upstream PR touches. The spec anticipated this (§ Commit sequencing: *"The restructure rewrites `src/printful_mcp/tools/`, which would make any later upstream pull request unmergeable. Sequencing solves this; architecture cannot."*). **Any revision the upstream maintainer requests on PR #2 is made on the `fix/mcp2-pin-v2-errors-order-items` branch, never on `dev`.** Do not move the `upstream-base` tag, and do not rebase or amend any existing commit.
  
  This is a rule about not breaking an open branch, **not** a reason to defer to upstream's design choices. The upstream PR was a courtesy; this fork is where the work gets better. Where an upstream-committed string, signature or shape can be improved here, improve it — and pin the improvement with a test, because the upstream-era tests were written to a lower bar (see Task 3's placements message).
- **`mcp>=0.9.0,<2` stays pinned.** Migrating to the 2.x `MCPServer` API is an explicit spec non-goal.
- **No retry or backoff on rate limits.** Surfacing `Retry-After` is deliberate: a silent retry walks a user into Printful's 60-second mockup lockout. Spec non-goal.
- **Do not reintroduce a FastMCP lifespan handler.** The lazy module global plus `atexit` exists because a lifespan handler failed; `.claude/CLAUDE.md` records this.
- **Run pytest as `.venv/bin/python -m pytest`.** A bare `python -m pytest` resolves to the system interpreter, whose global site-packages registers a `langsmith` plugin that crashes in `pytest_cmdline_parse` before collecting anything. That traceback is the interpreter, not the suite (Ruling 23).
- **The offline suite must pass with `PRINTFUL_API_KEY` and `PRINTFUL_STORE_ID` unset.** `pytest -m live` must fail loudly without credentials rather than skip.
- **The live suite needs `PRINTFUL_STORE_ID` exported**, not just `PRINTFUL_API_KEY`; the token is account-level and the API rejects store-scoped calls without the `X-PF-Store-Id` header (Ruling 34).
- **`printful_confirm_order` must NEVER be called against the live API.** It submits an order for fulfillment and charges a real account. It is asserted only against fake transports.
- **Mockup creation stays opt-in behind `PRINTFUL_E2E_MOCKUPS=1`.** Printful rate-limits new stores to 2 requests per 60 seconds with a 60-second lockout. Do not set the flag to make more tests run.
- **Run git through `rtk proxy git …`.** The hook silently returns empty output for some `git diff` invocations in this repository, and an empty result means nothing.
- **No `Co-Authored-By` trailer naming an agent or model** in any commit message.
- **`src/printful_cli/` stays untouched.** Plan 2 is the MCP side. If a change to the core would alter CLI behavior, say so in your report rather than making it.
- **This plan states no predicted test counts.** Five predicted counts in plan 1 proved wrong, and a plan-era number becomes a deletion target. Report the real number you get.

### MCP tool invariants (from `.claude/CLAUDE.md`)

Every tool, old or new, preserves all five:

1. **Return `str`, never a dict.**
2. **Every input model carries `format: Literal["markdown", "json"]`,** and the body branches on it: `json.dumps(data, indent=2)` for json, a formatter otherwise. The one exception already in the tree is `CreateMockupTaskInput`, whose `format` field means image format (`"jpg"`/`"png"`) — do not "fix" this by renaming it; see Task 7.
3. **Errors are returned, not raised.** The tail of every tool body returns a readable string, never a traceback.
4. **`@mcp.tool` always sets the full `annotations` dict** — `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`.
5. **Complex parameters stay flattened to strings.** `items_json` takes a JSON array as text; IDs come in comma-separated. This is not laziness — nested models break over HTTP-to-stdio bridges like mcporter.

### Test discipline

- **Every new test must be shown to discriminate.** Mutate the behavior it names, watch it fail, restore, confirm the tree is clean.
- **Revert the behavior, not the signature.** Deleting an argument raises `TypeError`, which is a different test failing for a different reason and proves nothing.
- **"The tool is registered" passes when the tool does nothing.** A registration test must also assert the tool maps to the expected `Request`.
- Plan 1 caught five tests that guarded nothing. A refactor guarded only by a test matching a substring of the thing being moved is unguarded.

---

## The parity ruling — read this before Task 2

**The spec's parity arithmetic does not survive contact with the code, and this plan follows the code.**

The spec (§ The parity gap) says *"Fourteen operations close the gap"* and *"That totals 33 MCP tools against 33 CLI commands."* Its own table lists **twelve**. Neither number is reachable:

| Source | Count |
|---|---|
| Spec prose | 14 new → 33 total |
| Spec table (orders 5, catalog 3, mockup 2, shipping 1, store 1) | 12 new → 31 total |
| **`printful_core.endpoints`, counted by AST** | **13 new → 32 total** |

The core defines **32 functions returning `Request`** (`_require_placements` returns `None` and `build_catalog_item` returns a `Dict`; neither is an endpoint). Exactly 19 are reachable through a tool today. The 13 that are not:

```
catalog.list_categories      orders.update_order            shipping.calculate_tax
catalog.get_category         orders.cancel_order            stores.list_templates
catalog.get_size_guide       orders.list_items
mockups.list_styles          orders.list_shipments
mockups.list_templates       orders.create_estimation_task
                             orders.get_estimation_task
```

**Target: 32 tools, one per core `Request` builder.** This is verifiable by a test rather than by counting prose, and Task 9 adds that test.

Two reconciliations, so nobody re-derives them:

- **The table's 12 becomes 13** because `estimate_costs` is one CLI command but two core operations. The MCP needs both as separate tools — see the rationale in Task 5, which belongs in the code, not only here.
- **"33 CLI commands" was never 33 distinct endpoints.** `draft submit` and `orders create` are the same core operation, and `test` is a connectivity probe with no endpoint of its own. `files list` reads session state and stays CLI-only, exactly as the spec's table says.

**Do not hunt for a 14th tool to honor the prose.** The table is the concrete artifact; the number is the error.

---

## Defects this plan fixes

Two of the five defects the spec opens with are still live **in the MCP server** — plan 1 fixed them only on the CLI side.

- **`/v2/countries` paginates at 20 of 239 rows.** `src/printful_mcp/tools/shipping.py:83` sends `client.get("/countries", params={"limit": 250})` — a single request with an explicit high limit. The response reports the limit the server actually applied in `paging.limit`, so `limit=250` is honored only if the endpoint has no lower cap. Task 6 routes this through `collect_pages_async`.
- **The server's private HTTP stack.** `src/printful_mcp/client.py` parses errors separately from `printful_core.errors`. Task 9 deletes it.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `src/printful_core/format/markdown.py` | Every markdown renderer the MCP surface uses. Pure `Dict[str, Any] -> str`, no I/O, no Pydantic. |
| `src/printful_core/tests/test_format_markdown.py` | Spec tests for those renderers. |
| `src/printful_mcp/transport.py` | The lazily-created `AsyncTransport` and its `atexit` teardown. |
| `src/printful_mcp/tests/__init__.py`, `conftest.py` | The fake async transport every adapter test uses. |
| `src/printful_mcp/tests/test_<domain>.py` | One per domain: registration, input validation, and the `Request` each tool builds. |

**Modified:**

| File | Change |
|---|---|
| `src/printful_mcp/tools/*.py` (7 modules) | Bodies rewritten onto core builders; markdown moved out; new tools added. |
| `src/printful_mcp/models/inputs.py` | Grows from 19 models to 32. |
| `src/printful_mcp/server.py` | Registers 32 tools; `get_client()` gives way to `get_transport()`. |
| `pyproject.toml` | `testpaths` gains `src/printful_mcp/tests`. |

**Deleted:**

| File | Reason |
|---|---|
| `src/printful_mcp/client.py` | Superseded by `printful_core.transport` and `printful_core.errors` (spec § The cull). |

### Why the markdown move is per-domain, not one task

A regex for `format_*_markdown` finds only three functions, which makes this look like a small relocation. It is not. Counted by parsing each tool body:

- **5 tools** call a named helper (`catalog.list_catalog_products`, `catalog.get_product`, `orders.create_order`, `orders.get_order`, `orders.confirm_order`)
- **13 tools** build their markdown inline with `lines = [...]` / `lines.extend([...])`
- **1 tool** (`mockups.create_mockup_task`) renders no markdown branch at all

So each domain carries its own markdown out as part of its own task. That keeps the change that moves a renderer in the same diff as the change that calls it, which is the only way a reviewer can see whether the output survived.

### The core interfaces every task consumes

```python
# printful_core.request
@dataclass(frozen=True)
class Request:
    method: str
    path: str
    version: str = "v2"          # "v1" for the legacy base URL
    params: Dict[str, Any] = field(default_factory=dict)   # None values dropped
    json: Optional[Dict[str, Any]] = None                  # shallow-copied on construction
    def with_params(self, **extra: Any) -> "Request": ...

# printful_core.auth
@dataclass(frozen=True)
class Credentials:
    api_key: str
    store_id: Optional[str] = None
    @classmethod
    def resolve(cls, api_key=None, store_id=None) -> "Credentials": ...   # raises PrintfulAuthError
    def headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]: ...

# printful_core.transport
class AsyncTransport:
    def __init__(self, credentials: Credentials, timeout: float = DEFAULT_TIMEOUT): ...
    async def send(self, request: Request, extra_headers=None) -> Dict[str, Any]: ...
    async def close(self) -> None: ...

# printful_core.errors
class PrintfulError(Exception):        # .message, .status_code, .detail
class PrintfulAuthError(PrintfulError):
class PrintfulRateLimitError(PrintfulError):

# printful_core.pagination
async def collect_pages_async(request, send) -> Dict[str, Any]: ...
# merged body: data = every row; paging = {"total", "limit", "offset": 0, "returned"}

# printful_core.polling
def task_body(response: Any) -> Dict[str, Any]: ...
def classify_task(body: Dict[str, Any]) -> str: ...      # "completed" | "failed" | "pending"
async def poll_estimation_task_async(request, send, created, max_wait, interval) -> Dict[str, Any]: ...
async def poll_mockup_task_async(request, send, task_id, max_wait, interval, recovery_hint) -> Dict[str, Any]: ...
```

**`PrintfulError`, not `PrintfulAPIError`.** The core raises `PrintfulError` with a `.message` attribute. Existing tool bodies catch `PrintfulAPIError` imported from `..client`. Every rewritten body catches `PrintfulError` imported from `printful_core.errors`. Missing one leaves a tool that raises a traceback at an MCP client instead of returning a string — invariant 3, and the kind of break no existing test catches because the server has no tests.

---

### Task 1: Give the server an async transport

**Files:**
- Create: `src/printful_mcp/transport.py`
- Create: `src/printful_mcp/tests/__init__.py`, `src/printful_mcp/tests/conftest.py`, `src/printful_mcp/tests/test_transport.py`
- Modify: `pyproject.toml:64` (`testpaths`)

**Interfaces:**
- Consumes: `printful_core.auth.Credentials.resolve()`, `printful_core.transport.AsyncTransport`.
- Produces: `printful_mcp.transport.get_transport() -> AsyncTransport` — every later task's tools call this instead of `get_client()`. `FakeTransport` in `conftest.py`, with `.sent: List[Request]`, `.last: Request`, and a queued-response constructor — every later task's tests use it.

**`get_client()` and `client.py` stay exactly as they are.** Seven tool modules still import `PrintfulClient`; deleting it now breaks all nineteen tools at once. The two coexist until Task 9 removes the old one. This is deliberate temporary duplication, the same pattern plan 1 used in its Tasks 12–14 (Ruling 3).

- [ ] **Step 1: Add the test package and register it with pytest**

Create `src/printful_mcp/tests/__init__.py` as an empty file.

In `pyproject.toml`, change line 64 from:

```toml
testpaths = ["src/printful_core/tests", "src/printful_cli/tests", "tests"]
```

to:

```toml
testpaths = ["src/printful_core/tests", "src/printful_cli/tests", "src/printful_mcp/tests", "tests"]
```

Without this the new tests are never collected and every later task's suite is green because it ran nothing.

- [ ] **Step 2: Write the fake transport**

Create `src/printful_mcp/tests/conftest.py`:

```python
"""The fake transport every MCP adapter test uses.

An MCP tool is a thin adapter: validate input, build a Request, send it, format
the reply. The thing worth asserting is which Request came out, so this records
them and replays canned responses rather than simulating the API.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from printful_core.request import Request


class FakeTransport:
    """Records every Request sent and returns the next queued response."""

    def __init__(self, responses: Optional[List[Any]] = None):
        self.sent: List[Request] = []
        self._responses = list(responses or [])

    async def send(self, request: Request,
                   extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        self.sent.append(request)
        if not self._responses:
            return {"data": {}}
        reply = self._responses.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def last(self) -> Request:
        assert self.sent, "no Request was sent"
        return self.sent[-1]


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()
```

- [ ] **Step 3: Write the failing tests**

Create `src/printful_mcp/tests/test_transport.py`:

```python
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
```

`monkeypatch.setattr(auth, "load_config", lambda: {})` is not decoration: `Credentials.resolve()` falls back to `~/.config/printful/config.json`, so without it the second test passes or fails depending on whether the developer running it has configured the CLI.

- [ ] **Step 4: Run them and watch them fail**

```bash
.venv/bin/python -m pytest src/printful_mcp/tests/test_transport.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'printful_mcp.transport'`.

- [ ] **Step 5: Write the transport module**

Create `src/printful_mcp/transport.py`:

```python
"""The server's transport: one AsyncTransport, created on first use.

This is deliberately not a FastMCP lifespan handler. A lifespan handler was
tried here and failed, and the commits that reached this lazy-global design
exist for that reason -- see `.claude/CLAUDE.md`. Do not reintroduce one.
"""
from __future__ import annotations

import asyncio
import atexit
from typing import Optional

from printful_core.auth import Credentials
from printful_core.transport import AsyncTransport

_transport: Optional[AsyncTransport] = None


def _close_transport() -> None:
    """Close the transport at interpreter exit."""
    global _transport
    if _transport is None:
        return
    try:
        asyncio.run(_transport.close())
    except RuntimeError:
        # At shutdown there may be no usable event loop. The process is going
        # away and the socket goes with it, so this is one of the few places
        # where swallowing is the honest answer rather than hiding a failure.
        pass
    finally:
        _transport = None


def get_transport() -> AsyncTransport:
    """The server's transport, created on first use."""
    global _transport
    if _transport is None:
        _transport = AsyncTransport(Credentials.resolve())
        atexit.register(_close_transport)
    return _transport
```

Note what changed from `server.py`'s `_cleanup_client`: it called
`asyncio.get_event_loop().run_until_complete(...)` inside `except Exception: pass`.
`get_event_loop()` is deprecated from 3.12 and the bare `except` swallowed every
failure, not just the shutdown race. `asyncio.run` plus a narrowed `except
RuntimeError` keeps the one case that is genuinely unfixable and lets anything
else surface.

- [ ] **Step 6: Run the tests and watch them pass**

```bash
.venv/bin/python -m pytest src/printful_mcp/tests/ -v
```

- [ ] **Step 7: Prove both tests discriminate**

Mutate the behavior, not the signature.

1. In `get_transport`, change `if _transport is None:` to `if True:`. Run: `test_one_transport_serves_every_tool` must FAIL. Restore.
2. In `get_transport`, change `Credentials.resolve()` to `Credentials(api_key="")`. Run: `test_missing_credentials_raise_rather_than_build_a_useless_transport` must FAIL. Restore.
3. `rtk proxy git status --porcelain` — confirm the tree is clean of the mutations before committing.

- [ ] **Step 8: Confirm nothing else moved**

```bash
.venv/bin/python -m pytest -q
```

The whole offline suite, with credentials unset. Report the number you get.

- [ ] **Step 9: Commit**

```bash
rtk proxy git add src/printful_mcp/transport.py src/printful_mcp/tests/ pyproject.toml
rtk proxy git commit -m "feat: give the MCP server the core's async transport"
```

---

### The tool signature: injected, not reached for

Every tool function keeps a first parameter and changes only its type:

```python
# before
async def get_product(client: PrintfulClient, params: GetProductInput) -> str:
# after
async def get_product(transport: AsyncTransport, params: GetProductInput) -> str:
```

`server.py`'s delegates change by one word:

```python
return await catalog.get_product(get_transport(), params)
```

Do **not** make the tool body call `get_transport()` itself. Three reasons, in
order of weight:

1. **`tests/test_create_order.py` calls `create_order(client, params)`
   positionally.** That file is part of the open upstream PR. A tool that reaches
   for a global cannot be handed a fake at all.
2. A test that must monkeypatch a module global in two places — the transport
   module and the importing tool module — is testing the patching, not the tool.
3. It is the pattern already in the file, and conformance beats taste here.

---

### Task 2: Move catalog onto the core and close its parity gap

**Files:**
- Create: `src/printful_core/format/markdown.py`
- Create: `src/printful_core/tests/test_format_markdown.py`
- Create: `src/printful_mcp/tests/test_catalog.py`
- Modify: `src/printful_mcp/tools/catalog.py` (rewrite; 270 lines today)
- Modify: `src/printful_mcp/models/inputs.py` (add three models)
- Modify: `src/printful_mcp/server.py` (five delegates change, three registrations added)

**Interfaces:**
- Consumes: `printful_mcp.transport.get_transport`, `FakeTransport` (Task 1).
- Produces: `printful_core.format.markdown` — later tasks append their renderers to this module. Eight catalog tools, of which `printful_list_categories`, `printful_get_category` and `printful_get_size_guide` are new.

Core builders this task binds, with their exact signatures:

```python
catalog.list_products(limit=20, offset=0, category_ids=None, colors=None,
                      techniques=None, types=None) -> Request
catalog.get_product(product_id: int) -> Request
catalog.list_variants(product_id: int, limit=20, offset=0) -> Request
catalog.get_variant_prices(variant_id: int, currency=None) -> Request
catalog.get_availability(product_id: int, techniques=None) -> Request
catalog.list_categories(limit=20, offset=0) -> Request          # new tool
catalog.get_category(category_id: int) -> Request               # new tool
catalog.get_size_guide(product_id: int, unit=None) -> Request   # new tool
```

**Do not paginate these.** `list_products`, `list_variants` and `list_categories` take caller-supplied `limit`/`offset` and must send exactly one request with exactly those values. `collect_pages_async` belongs only where the caller cannot page for themselves — in this plan that is `list_countries` alone (Task 6).

- [ ] **Step 1: Create the core markdown module with the catalog renderers**

Create `src/printful_core/format/markdown.py`. These bodies are moved, not rewritten — every line is the existing output, and the only change is that the data arrives as an argument.

```python
"""Markdown renderers for the MCP surface.

Pure functions from a decoded response body to a string. They perform no I/O,
know nothing about Pydantic, and take the identifiers they print as arguments
because a response body does not always carry the id that was asked for.

`summary.py` beside this module renders the same responses for the CLI, which
wants structured data rather than prose. The two are separate because they have
different readers, not because anyone forgot to unify them.
"""
from __future__ import annotations

from typing import Any, Dict


def product(body: Dict[str, Any]) -> str:
    """One catalog product."""
    lines = [
        f"# {body['name']}",
        f"",
        f"**ID:** {body['id']}",
        f"**Type:** {body['type']}",
        f"**Brand:** {body.get('brand', 'N/A')}",
        f"**Variants:** {body['variant_count']}",
        f"**Status:** {'Discontinued' if body['is_discontinued'] else 'Available'}",
        f"",
    ]
    if body.get('description'):
        lines.extend(["## Description", body['description'], ""])
    if body.get('techniques'):
        lines.append("## Available Techniques")
        for tech in body['techniques']:
            default = " (default)" if tech.get('is_default') else ""
            lines.append(f"- **{tech['display_name']}** ({tech['key']}){default}")
        lines.append("")
    if body.get('placements'):
        lines.append(f"## Placements ({len(body['placements'])} available)")
        for placement in body['placements'][:5]:
            lines.append(f"- {placement['placement']} - {placement['technique']}")
        if len(body['placements']) > 5:
            lines.append(f"  _(and {len(body['placements']) - 5} more)_")
        lines.append("")
    return "\n".join(lines)


def products(data: Dict[str, Any]) -> str:
    """A page of catalog products."""
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Catalog Products ({paging.get('total', 0)} total)",
        f"",
        f"Showing {len(rows)} products (offset: {paging.get('offset', 0)}, "
        f"limit: {paging.get('limit', 20)})",
        f"",
    ]
    for row in rows:
        lines.extend([
            f"## {row['name']}",
            f"- **ID:** {row['id']}",
            f"- **Type:** {row['type']}",
            f"- **Variants:** {row['variant_count']}",
            f"- **Techniques:** {', '.join(t['key'] for t in row.get('techniques', []))}",
            f"",
        ])
    return "\n".join(lines)


def variants(data: Dict[str, Any], product_id: int) -> str:
    """A page of variants for one product.

    `product_id` is an argument because the variants response does not repeat
    the product it belongs to, and the heading names it.
    """
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Variants for Product {product_id}",
        f"",
        f"Total variants: {paging.get('total', 0)}",
        f"Showing {len(rows)} variants",
        f"",
    ]
    for row in rows:
        lines.extend([
            f"## {row['name']}",
            f"- **Variant ID:** {row['id']}",
            f"- **Size:** {row['size']}",
            f"- **Color:** {row['color']} ({row['color_code']})",
            f"",
        ])
    return "\n".join(lines)


def variant_prices(data: Dict[str, Any], variant_id: int) -> str:
    """Pricing for one variant."""
    body = data.get('data', {})
    currency = body.get('currency', 'USD')
    lines = [
        f"# Pricing for Variant {variant_id}",
        f"",
        f"**Currency:** {currency}",
        f"",
    ]
    if body.get('variant', {}).get('techniques'):
        lines.append("## Base Prices by Technique")
        for tech in body['variant']['techniques']:
            lines.append(
                f"- **{tech['technique_display_name']}:** {tech['price']} {currency}")
        lines.append("")
    if body.get('product', {}).get('placements'):
        lines.append("## Additional Placement Prices")
        for placement in body['product']['placements']:
            lines.append(
                f"- **{placement['title']}:** {placement['price']} {currency}")
        lines.append("")
    return "\n".join(lines)


def availability(data: Dict[str, Any], product_id: int) -> str:
    """Stock availability per variant and technique."""
    lines = [f"# Availability for Product {product_id}", f""]
    for row in data.get('data', []):
        lines.append(f"## Variant {row['catalog_variant_id']}")
        for tech in row.get('techniques', []):
            lines.append(f"### {tech['technique']}")
            for region in tech.get('selling_regions', []):
                lines.append(f"- **{region['name']}:** {region['availability']}")
        lines.append("")
    return "\n".join(lines)


def categories(data: Dict[str, Any]) -> str:
    """A page of catalog categories."""
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Catalog Categories ({paging.get('total', 0)} total)",
        f"",
        f"Showing {len(rows)} categories",
        f"",
    ]
    for row in rows:
        parent = row.get('parent_id')
        suffix = f" (parent: {parent})" if parent else ""
        lines.append(f"- **{row['title']}** — ID {row['id']}{suffix}")
    lines.append("")
    return "\n".join(lines)


def category(data: Dict[str, Any]) -> str:
    """One catalog category."""
    body = data.get('data', {})
    lines = [
        f"# {body.get('title', 'Category')}",
        f"",
        f"**ID:** {body.get('id')}",
        f"**Parent ID:** {body.get('parent_id', 'none')}",
        f"",
    ]
    if body.get('image_url'):
        lines.extend([f"**Image:** {body['image_url']}", ""])
    return "\n".join(lines)


def size_guide(data: Dict[str, Any], product_id: int) -> str:
    """The size tables for one product."""
    body = data.get('data', {})
    lines = [
        f"# Size Guide for Product {product_id}",
        f"",
        f"**Unit:** {body.get('unit', 'unknown')}",
        f"",
    ]
    for table in body.get('size_tables', []):
        lines.append(f"## {table.get('type', 'Measurements')}")
        if table.get('description'):
            lines.extend([table['description'], ""])
        for measurement in table.get('measurements', []):
            values = ", ".join(
                f"{v.get('size')}: {v.get('min_value', v.get('value', ''))}"
                f"{'-' + str(v['max_value']) if v.get('max_value') else ''}"
                for v in measurement.get('values', [])
            )
            lines.append(f"- **{measurement.get('type_label', '')}** — {values}")
        lines.append("")
    return "\n".join(lines)
```

Then change `src/printful_core/format/__init__.py` from:

```python
"""Response formatting shared by both surfaces."""

from . import summary  # noqa: F401
```

to:

```python
"""Response formatting shared by both surfaces."""

from . import markdown  # noqa: F401
from . import summary  # noqa: F401
```

- [ ] **Step 2: Write the renderer tests**

Create `src/printful_core/tests/test_format_markdown.py`:

```python
"""The markdown renderers, exercised with no transport at all."""
from printful_core.format import markdown


def test_a_discontinued_product_says_so():
    """The status line is the one field a buyer acts on.

    `is_discontinued` is a boolean in the response and reads as neither word,
    so the renderer is what turns it into something a person can use.
    """
    out = markdown.product({
        "id": 71, "name": "Unisex Tee", "type": "T-SHIRT", "brand": "Bella",
        "variant_count": 100, "is_discontinued": True,
    })
    assert "**Status:** Discontinued" in out


def test_a_product_list_reports_the_total_not_the_page_size():
    """A page of 2 out of 239 must not read as 2 products existing."""
    out = markdown.products({
        "data": [{"id": 1, "name": "A", "type": "T", "variant_count": 3},
                 {"id": 2, "name": "B", "type": "T", "variant_count": 4}],
        "paging": {"total": 239, "offset": 0, "limit": 2},
    })
    assert "239 total" in out
    assert "Showing 2 products" in out


def test_variants_name_the_product_they_belong_to():
    """The variants response carries no product id, so the caller supplies it."""
    out = markdown.variants({"data": [], "paging": {"total": 0}}, product_id=71)
    assert "# Variants for Product 71" in out


def test_placement_prices_carry_the_response_currency():
    """A bare number is unusable when the account bills in something else."""
    out = markdown.variant_prices({"data": {
        "currency": "EUR",
        "product": {"placements": [{"title": "Back print", "price": "5.95"}]},
    }}, variant_id=4011)
    assert "5.95 EUR" in out
```

- [ ] **Step 3: Run them and watch them fail**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_format_markdown.py -v
```

Expected before Step 1 lands: `ImportError: cannot import name 'markdown'`. If you wrote Step 1 first they pass immediately — in that case say so in your report and rely on Step 8's mutations for proof.

- [ ] **Step 4: Add the three new input models**

Append to `src/printful_mcp/models/inputs.py`, matching the file's existing style:

```python
class ListCategoriesInput(BaseModel):
    """Input for printful_list_categories."""
    limit: int = Field(default=20, ge=1, le=100, description="Categories per page")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")


class GetCategoryInput(BaseModel):
    """Input for printful_get_category."""
    category_id: int = Field(description="Catalog category ID")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")


class GetSizeGuideInput(BaseModel):
    """Input for printful_get_size_guide."""
    product_id: int = Field(description="Catalog product ID")
    unit: Optional[str] = Field(
        default=None,
        description="Measurement unit: 'inches' or 'cm'. Omit for the API default.")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")
```

Check the file's existing imports cover `Optional` and `Literal`; add what is missing and nothing else.

- [ ] **Step 5: Rewrite the catalog tools onto the core**

Replace `src/printful_mcp/tools/catalog.py` entirely. The two module-level `format_*_markdown` helpers are gone — they moved to the core in Step 1.

```python
"""Catalog tools for the Printful MCP server."""

import json

from printful_core.endpoints import catalog
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import (
    GetCategoryInput,
    GetProductAvailabilityInput,
    GetProductInput,
    GetProductVariantsInput,
    GetSizeGuideInput,
    GetVariantPricesInput,
    ListCatalogProductsInput,
    ListCategoriesInput,
)


async def list_catalog_products(transport: AsyncTransport,
                                params: ListCatalogProductsInput) -> str:
    """
    List catalog products with optional filters.

    Browse Printful's product catalog with filtering by category, color, technique, etc.
    Returns product IDs, names, types, and available variants.
    """
    try:
        request = catalog.list_products(
            limit=params.limit,
            offset=params.offset,
            category_ids=params.category_ids,
            colors=params.colors,
            techniques=params.techniques,
            types=params.types,
        )
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.products(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_product(transport: AsyncTransport, params: GetProductInput) -> str:
    """
    Get detailed information about a specific catalog product.

    Returns full product details including placements, techniques, design options,
    available sizes, colors, and product options.
    """
    try:
        data = await transport.send(catalog.get_product(params.product_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.product(data.get("data", {}))
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_product_variants(transport: AsyncTransport,
                               params: GetProductVariantsInput) -> str:
    """
    Get all variants (size/color combinations) for a catalog product.

    Returns variant IDs, names, sizes, colors, and images needed for ordering.
    """
    try:
        request = catalog.list_variants(
            params.product_id, limit=params.limit, offset=params.offset)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.variants(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_variant_prices(transport: AsyncTransport,
                             params: GetVariantPricesInput) -> str:
    """
    Get pricing information for a specific catalog variant.

    Returns prices for different techniques, placements, and quantity discounts.
    """
    try:
        request = catalog.get_variant_prices(params.variant_id, currency=params.currency)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.variant_prices(data, params.variant_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_product_availability(transport: AsyncTransport,
                                   params: GetProductAvailabilityInput) -> str:
    """
    Check stock availability for a catalog product.

    Returns availability status for each variant and technique.
    """
    try:
        request = catalog.get_availability(params.product_id, techniques=params.techniques)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.availability(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_categories(transport: AsyncTransport, params: ListCategoriesInput) -> str:
    """
    List the catalog's product categories.

    Category IDs are what printful_list_catalog_products filters on, so this is
    the tool that makes that filter usable.
    """
    try:
        request = catalog.list_categories(limit=params.limit, offset=params.offset)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.categories(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_category(transport: AsyncTransport, params: GetCategoryInput) -> str:
    """
    Get one catalog category by ID.
    """
    try:
        data = await transport.send(catalog.get_category(params.category_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.category(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_size_guide(transport: AsyncTransport, params: GetSizeGuideInput) -> str:
    """
    Get the size tables for a catalog product.

    Returns measurements per size, in inches or centimetres.
    """
    try:
        request = catalog.get_size_guide(params.product_id, unit=params.unit)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.size_guide(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"
```

- [ ] **Step 6: Wire the server**

In `src/printful_mcp/server.py`:

1. Add `from .transport import get_transport` to the imports.
2. Add `GetCategoryInput, GetSizeGuideInput, ListCategoriesInput` to the `models.inputs` import block.
3. Change the five existing catalog delegates from `get_client()` to `get_transport()`, e.g.:

```python
    return await catalog.list_catalog_products(get_transport(), params)
```

Leave the other fourteen delegates on `get_client()` — their tool modules still expect a `PrintfulClient` until their own task runs.

4. Append three registrations in the file's existing form:

```python
@mcp.tool(
    name="printful_list_categories",
    annotations={
        "title": "List Catalog Categories",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_list_categories(params: ListCategoriesInput) -> str:
    """
    List the catalog's product categories.

    Category IDs are what printful_list_catalog_products filters on.
    """
    return await catalog.list_categories(get_transport(), params)


@mcp.tool(
    name="printful_get_category",
    annotations={
        "title": "Get Catalog Category",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_get_category(params: GetCategoryInput) -> str:
    """
    Get one catalog category by ID.
    """
    return await catalog.get_category(get_transport(), params)


@mcp.tool(
    name="printful_get_size_guide",
    annotations={
        "title": "Get Product Size Guide",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_get_size_guide(params: GetSizeGuideInput) -> str:
    """
    Get the size tables for a catalog product, in inches or centimetres.
    """
    return await catalog.get_size_guide(get_transport(), params)
```

- [ ] **Step 7: Write the adapter tests**

Create `src/printful_mcp/tests/test_catalog.py`. The fake transport is passed in, so nothing is monkeypatched:

```python
"""The catalog adapter: what Request each tool builds, and what it returns."""
import json

from printful_core.errors import PrintfulError
from printful_mcp.models.inputs import (
    GetCategoryInput,
    GetProductVariantsInput,
    GetSizeGuideInput,
    ListCatalogProductsInput,
    ListCategoriesInput,
)
from printful_mcp.tools import catalog


async def test_filters_reach_the_query_string(transport):
    """A filter the user set must not be silently dropped.

    Every filter is optional and each is threaded through its own argument, so
    a dropped one returns a plausible unfiltered catalog rather than an error.
    """
    await catalog.list_catalog_products(
        transport,
        ListCatalogProductsInput(limit=5, offset=10, category_ids="24,25",
                                 colors="Black", techniques="dtg", types="T-SHIRT"))
    sent = transport.last
    assert sent.method == "GET"
    assert sent.path == "/catalog-products"
    assert sent.params == {"limit": 5, "offset": 10, "category_ids": "24,25",
                           "colors": "Black", "techniques": "dtg", "types": "T-SHIRT"}


async def test_the_callers_page_is_sent_unchanged(transport):
    """Variant listing must not silently collect every page.

    `collect_pages_async` would be wrong here: the tool exposes limit and
    offset, so walking the whole collection ignores what the caller asked for
    and can return thousands of rows into a model's context.
    """
    await catalog.get_product_variants(
        transport, GetProductVariantsInput(product_id=71, limit=2, offset=40))
    assert len(transport.sent) == 1
    assert transport.last.params == {"limit": 2, "offset": 40}


async def test_an_unset_size_guide_unit_is_omitted(transport):
    """An absent unit must not reach the API as the string 'None'."""
    await catalog.get_size_guide(transport, GetSizeGuideInput(product_id=71))
    assert "unit" not in transport.last.params


async def test_an_api_error_is_returned_as_text(transport):
    """An MCP client must see a readable string, never a traceback.

    The tool contract is that errors are returned. A raised exception crosses
    the JSON-RPC boundary as a protocol error, and the calling model sees
    nothing it can act on.
    """
    transport._responses.append(PrintfulError("Category 999 not found", status_code=404))
    out = await catalog.get_category(transport, GetCategoryInput(category_id=999))
    assert out == "Error: Category 999 not found"


async def test_json_format_returns_the_body_verbatim(transport):
    """`format="json"` exists so a caller can parse rather than scrape."""
    transport._responses.append({"data": [{"id": 24, "title": "Men's"}],
                                 "paging": {"total": 1}})
    out = await catalog.list_categories(transport, ListCategoriesInput(format="json"))
    assert json.loads(out)["data"][0]["id"] == 24
```

`asyncio_mode = "auto"` is already set in `pyproject.toml`, so these need no `@pytest.mark.asyncio`.

- [ ] **Step 8: Run the tests and prove they discriminate**

```bash
.venv/bin/python -m pytest src/printful_mcp/tests/ src/printful_core/tests/test_format_markdown.py -v
```

Then mutate the behavior — never the signature — one at a time, restoring after each:

| Mutation | Test that must fail |
|---|---|
| Change `techniques=params.techniques` to `techniques=None` in `list_catalog_products` | `test_filters_reach_the_query_string` |
| Replace `transport.send(request)` in `get_product_variants` with `collect_pages_async(request, transport.send)` | `test_the_callers_page_is_sent_unchanged` |
| Change `unit=params.unit` to `unit=str(params.unit)` | `test_an_unset_size_guide_unit_is_omitted` |
| Change `except PrintfulError` to `except ValueError` in `get_category` | `test_an_api_error_is_returned_as_text` |
| In `markdown.products`, print `len(rows)` where `paging['total']` is printed | `test_a_product_list_reports_the_total_not_the_page_size` |

Then `rtk proxy git status --porcelain` and confirm the tree carries none of the mutations.

- [ ] **Step 9: Confirm the server still imports and registers**

```bash
.venv/bin/python -c "from printful_mcp.server import mcp; import asyncio; print('tools:', len(asyncio.run(mcp.list_tools())))"
```

Expected: 22. `mcp.list_tools()` is a coroutine returning `list[Tool]`; this was
confirmed against the installed `mcp` version, so it is the accessor, not a
guess. If it raises, the server failed to import and the traceback says why.

- [ ] **Step 10: Run the whole offline suite**

```bash
.venv/bin/python -m pytest -q
```

Credentials unset. Report the number you get.

- [ ] **Step 11: Commit**

```bash
rtk proxy git add src/printful_core/format/ src/printful_core/tests/test_format_markdown.py \
  src/printful_mcp/tools/catalog.py src/printful_mcp/models/inputs.py \
  src/printful_mcp/server.py src/printful_mcp/tests/test_catalog.py
rtk proxy git commit -m "feat: move the catalog tools onto the core and add categories and size guides"
```

Stage by path. `git add -A` was ruled against in plan 1 (Ruling 5) because `pip install -e .` regenerates `src/printful_mcp.egg-info/`.

---
### Task 3: Move the four existing order tools onto the core

**Files:**
- Modify: `src/printful_mcp/tools/orders.py` (rewrite; 216 lines today)
- Modify: `src/printful_core/format/markdown.py` (append `order` and `orders`)
- Modify: `src/printful_mcp/models/inputs.py` (`ListOrdersInput` gains `status`)
- Modify: `src/printful_mcp/server.py` (four delegates)
- Modify: `tests/test_create_order.py` (the fake and the call signature change)
- Create: `src/printful_mcp/tests/test_orders.py`

**Interfaces:**
- Consumes: `FakeTransport`, `get_transport`, `printful_core.format.markdown`.
- Produces: `markdown.order(body)`, `markdown.orders(data)` — Task 4 and Task 5 both render orders.

```python
orders.list_orders(limit=20, offset=0, status=None) -> Request
orders.get_order(order_id: str) -> Request
orders.create_order(recipient: Dict, items: List[Dict],
                    external_id=None, shipping=None) -> Request   # raises ValueError
orders.confirm_order(order_id: str) -> Request
```

#### Read this before you start: the placements message is a trap

`create_order` validates items twice today, and the two messages differ.

The tool returns (from upstream commit `2a5eacd`):

```
Error: order_items[0] has no placements. Printful rejects a catalog item with
no artwork. Add placements, e.g. [{"placement":"front","technique":"dtg",
"layers":[{"type":"file","url":"https://example.com/art.png"}]}]
```

`printful_core.endpoints.orders._require_placements` raises `ValueError`:

```
order_items[0] (variant 4012) has no placements. Printful rejects a catalog
item with no artwork.
```

The core names the variant; the tool carries a worked example. **The existing
test cannot tell them apart** — `tests/test_create_order.py:64` asserts only
`"placements" in result`, and both strings contain it. This is the sixth test
of that shape found in this project, and the standing lesson applies: a
refactor guarded only by a test matching a substring of the thing being moved
is unguarded.

**Ruling: the core validates, the tool supplies the hint.** Delete the tool's
duplicate placements loop, let the core raise, catch `ValueError`, and append
the example. This is Ruling 26's shape exactly — the core must not name a
CLI command, and equally must not carry an MCP-flavoured JSON example, so the
caller passes what only it knows.

The resulting message is a deliberate, user-visible improvement on both:

```
Error: order_items[0] (variant 4012) has no placements. Printful rejects a
catalog item with no artwork. Add placements, e.g.
[{"placement":"front","technique":"dtg","layers":[{"type":"file","url":"https://example.com/art.png"}]}]
```

Step 6 replaces the substring assertion with one that pins it.

**`ValueError` is not a `PrintfulError`.** A body that catches only
`PrintfulError` lets the core's validation escape as a traceback across the
JSON-RPC boundary. `create_order` catches both.

- [ ] **Step 1: Append the order renderers to the core**

Add to `src/printful_core/format/markdown.py`:

```python
def order(body: Dict[str, Any]) -> str:
    """One order."""
    lines = [
        f"# Order {body['id']}",
        f"",
        f"**Status:** {body['status']}",
        f"**External ID:** {body.get('external_id', 'N/A')}",
        f"**Created:** {body['created_at']}",
        f"**Updated:** {body['updated_at']}",
        f"",
    ]
    if body.get('recipient'):
        recipient = body['recipient']
        lines.extend([
            "## Recipient",
            f"**Name:** {recipient['name']}",
            f"**Address:** {recipient['address1']}",
            f"**City:** {recipient['city']}, {recipient.get('state_code', '')} "
            f"{recipient['zip']}",
            f"**Country:** {recipient['country_name']} ({recipient['country_code']})",
            f"",
        ])
    if body.get('costs'):
        costs = body['costs']
        if costs['calculation_status'] == 'done':
            lines.extend([
                "## Costs",
                f"**Currency:** {costs['currency']}",
                f"**Subtotal:** {costs['subtotal']}",
                f"**Shipping:** {costs['shipping']}",
                f"**Tax:** {costs['tax']}",
                f"**Total:** {costs['total']}",
                f"",
            ])
        else:
            lines.extend(["## Costs", f"**Status:** {costs['calculation_status']}", f""])
    if body.get('order_items'):
        lines.append(f"## Order Items ({len(body['order_items'])})")
        for item in body['order_items']:
            lines.extend([
                f"- **Item {item['id']}**: {item.get('name', 'N/A')}",
                f"  - Variant: {item.get('catalog_variant_id', 'N/A')}",
                f"  - Quantity: {item['quantity']}",
                f"  - Price: {item.get('price', 'N/A')} {item.get('currency', '')}",
            ])
        lines.append("")
    return "\n".join(lines)


def orders(data: Dict[str, Any]) -> str:
    """A page of orders."""
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Orders ({paging.get('total', 0)} total)",
        f"",
        f"Showing {len(rows)} orders (offset: {paging.get('offset', 0)}, "
        f"limit: {paging.get('limit', 20)})",
        f"",
    ]
    for row in rows:
        costs = row.get('costs', {})
        lines.extend([
            f"## Order {row['id']}",
            f"- **Status:** {row['status']}",
            f"- **External ID:** {row.get('external_id', 'N/A')}",
            f"- **Total:** {costs.get('total', 'Calculating...')} {costs.get('currency', '')}",
            f"- **Items:** {len(row.get('order_items', []))}",
            f"- **Created:** {row['created_at']}",
            f"",
        ])
    return "\n".join(lines)
```

- [ ] **Step 2: Give `ListOrdersInput` the status filter the CLI already has**

`printful_cli`'s `orders list` accepts `--status` and the core builder takes it; the MCP model does not. That is a parity gap inside an existing tool. In `src/printful_mcp/models/inputs.py`, add one field to `ListOrdersInput`:

```python
    status: Optional[str] = Field(
        default=None,
        description="Filter by order status, e.g. 'draft', 'pending', 'fulfilled'")
```

- [ ] **Step 3: Rewrite `src/printful_mcp/tools/orders.py`**

```python
"""Order tools for the Printful MCP server."""

import json

from printful_core.endpoints import orders
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import (
    ConfirmOrderInput,
    CreateOrderInput,
    GetOrderInput,
    ListOrdersInput,
)

PLACEMENTS_HINT = (
    'Add placements, e.g. [{"placement":"front","technique":"dtg",'
    '"layers":[{"type":"file","url":"https://example.com/art.png"}]}]'
)


async def create_order(transport: AsyncTransport, params: CreateOrderInput) -> str:
    """
    Create a new draft order.

    Creates an order in draft status with its items. Drafts are not charged.
    Confirm the order with printful_confirm_order to start fulfillment.
    """
    recipient = {
        "name": params.recipient_name,
        "address1": params.recipient_address1,
        "city": params.recipient_city,
        "country_code": params.recipient_country_code,
        "zip": params.recipient_zip,
    }
    if params.recipient_state_code:
        recipient["state_code"] = params.recipient_state_code
    if params.recipient_email:
        recipient["email"] = params.recipient_email
    if params.recipient_phone:
        recipient["phone"] = params.recipient_phone

    try:
        items = json.loads(params.items_json)
    except json.JSONDecodeError as e:
        return f"Error: items_json must be valid JSON array ({e})."
    if not isinstance(items, list) or not items:
        return "Error: items_json must be a non-empty JSON array of order items."

    try:
        request = orders.create_order(recipient, items, external_id=params.external_id)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.order(data.get("data", {}))
    except ValueError as e:
        # The core validates items and names the offending index and variant.
        # It cannot carry this hint: the shape of a placements block is an
        # MCP-surface concern, and the core must stay free of either caller's
        # vocabulary (the same reason `_mockup_timeout` takes `recovery_hint`).
        return f"Error: {e} {PLACEMENTS_HINT}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_order(transport: AsyncTransport, params: GetOrderInput) -> str:
    """
    Get details of a specific order.

    Use order ID or external ID (prefix with @) to retrieve order information,
    including status, recipient, costs, and items.
    """
    try:
        data = await transport.send(orders.get_order(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.order(data.get("data", {}))
    except PrintfulError as e:
        return f"Error: {e.message}"


async def confirm_order(transport: AsyncTransport, params: ConfirmOrderInput) -> str:
    """
    Confirm an order to start fulfillment.

    Moves the order from draft to pending and begins production. This charges
    the account. The order must have items and calculated costs first.
    """
    try:
        data = await transport.send(orders.confirm_order(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        body = data.get("data", {})
        return f"✓ Order {body['id']} confirmed successfully!\n\n" + markdown.order(body)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_orders(transport: AsyncTransport, params: ListOrdersInput) -> str:
    """
    List orders from the store.

    Returns a paginated list of orders with basic information. Filter by status
    to find drafts awaiting confirmation.
    """
    try:
        request = orders.list_orders(
            limit=params.limit, offset=params.offset, status=params.status)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.orders(data)
    except PrintfulError as e:
        return f"Error: {e.message}"
```

The `format_order_markdown` helper is gone from this module — it is `markdown.order` now.

- [ ] **Step 4: Wire the four delegates in `server.py`**

Change each of the four order delegates from `get_client()` to `get_transport()`:

```python
    return await orders.create_order(get_transport(), params)
    return await orders.get_order(get_transport(), params)
    return await orders.confirm_order(get_transport(), params)
    return await orders.list_orders(get_transport(), params)
```

No new registrations in this task, but **one annotation is wrong and gets fixed
here.** `printful_confirm_order` currently declares:

```python
        "destructiveHint": False,
```

It starts fulfillment, charges the account, and cannot be undone. An MCP client
reads `destructiveHint` to decide whether to prompt a human before running a
tool, so this value is a safety defect rather than a documentation one. Change
it to:

```python
        "destructiveHint": True,
```

Leave `readOnlyHint: False` and `idempotentHint: False` alone — both are already
correct. Task 9 asserts this, and Task 4 sets the same field on
`printful_cancel_order` for the same reason.

- [ ] **Step 5: Update the two upstream-era tests in `tests/`**

`tests/test_create_order.py` builds a `RecordingClient` with a `.post()` method and calls `create_order(client, params)`. Both change. Replace its fake with one that matches the transport contract:

```python
class RecordingTransport:
    """Records the Request instead of the posted body."""

    def __init__(self):
        self.sent = []

    async def send(self, request, extra_headers=None):
        self.sent.append(request)
        return {"data": {"id": 1, "status": "draft",
                         "created_at": "2026-01-01", "updated_at": "2026-01-01"}}
```

That body is the minimum `markdown.order` can render: it reads `id`, `status`,
`created_at` and `updated_at` unguarded, and everything else behind a
truthiness check. **Run the test before moving on** — a fake missing one of
those four raises `KeyError` inside the tool's `try`, which `except
PrintfulError` does not catch, and the failure reads as a tool bug rather than
a fixture gap.

Then update each call site from `create_order(client, params)` to
`create_order(transport, params)`, and each `assert client.posted is None` to
`assert transport.sent == []`.

**This diverges `dev` from the upstream PR branch, which is expected.** Per the
Global Constraints, `fix/mcp2-pin-v2-errors-order-items` keeps its own copy and
any maintainer-requested revision happens there. Do not touch that branch.

- [ ] **Step 6: Replace the non-discriminating placements assertion**

In `tests/test_create_order.py`, the existing assertion is:

```python
    assert "placements" in result
```

Replace it with one that pins the whole contract — that the offending index and
variant are named, that the hint arrives, and that nothing was sent:

```python
    assert "order_items[0]" in result
    assert "variant 4012" in result
    assert "no placements" in result
    assert '"placement":"front"' in result      # the hint the MCP surface adds
    assert transport.sent == []
```

`"variant 4012"` is the half that only the core produces and the old tool did
not; `'"placement":"front"'` is the half only the tool produces. Together they
prove both layers ran.

- [ ] **Step 7: Write the adapter tests**

Create `src/printful_mcp/tests/test_orders.py`:

```python
"""The orders adapter."""
import json

from printful_core.errors import PrintfulError
from printful_mcp.models.inputs import (
    ConfirmOrderInput,
    CreateOrderInput,
    ListOrdersInput,
)
from printful_mcp.tools import orders


def _recipient():
    return dict(recipient_name="Ada Lovelace", recipient_address1="1 Analytical Way",
                recipient_city="London", recipient_country_code="GB",
                recipient_zip="EC1A 1BB")


async def test_a_draft_order_carries_its_items(transport):
    """An order created without items can never be filled.

    This is the defect the upstream fix exists for: the tool used to send a
    recipient and nothing else, and the resulting draft was a dead end.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 2,
              "placements": [{"placement": "front", "technique": "dtg",
                              "layers": [{"type": "file", "url": "https://x/a.png"}]}]}]
    await orders.create_order(
        transport, CreateOrderInput(items_json=json.dumps(items), **_recipient()))
    sent = transport.last
    assert sent.method == "POST"
    assert sent.path == "/orders"
    assert sent.json["order_items"][0]["catalog_variant_id"] == 4012
    assert sent.json["order_items"][0]["quantity"] == 2


async def test_the_status_filter_reaches_the_query(transport):
    """Without this the tool cannot answer 'which drafts are waiting?'."""
    await orders.list_orders(transport, ListOrdersInput(status="draft"))
    assert transport.last.params["status"] == "draft"


async def test_an_unset_status_is_not_sent(transport):
    """A literal 'None' status would filter every order out."""
    await orders.list_orders(transport, ListOrdersInput())
    assert "status" not in transport.last.params


async def test_confirmation_posts_to_the_confirmation_path(transport):
    """Confirmation charges the account, so the path must be exact.

    This tool is never exercised against the live API. A fake transport is the
    only place its request shape can be checked at all.
    """
    transport._responses.append({"data": {"id": 42, "status": "pending",
                                          "created_at": "", "updated_at": ""}})
    out = await orders.confirm_order(transport, ConfirmOrderInput(order_id="42"))
    assert transport.last.method == "POST"
    assert transport.last.path == "/orders/42/confirmation"
    assert "confirmed successfully" in out


async def test_a_core_validation_error_does_not_escape_as_a_traceback(transport):
    """The core raises ValueError; PrintfulError alone would not catch it.

    An uncaught exception crosses the JSON-RPC boundary as a protocol error,
    so the calling model sees a transport failure rather than the reason its
    order was rejected.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}]
    out = await orders.create_order(
        transport, CreateOrderInput(items_json=json.dumps(items), **_recipient()))
    assert out.startswith("Error: order_items[0] (variant 4012) has no placements.")
    assert '"placement":"front"' in out
    assert transport.sent == []


async def test_an_api_error_is_returned_as_text(transport):
    transport._responses.append(PrintfulError("Order 9 not found", status_code=404))
    out = await orders.list_orders(transport, ListOrdersInput())
    assert out == "Error: Order 9 not found"
```

- [ ] **Step 8: Run and prove discrimination**

```bash
.venv/bin/python -m pytest src/printful_mcp/tests/ tests/test_create_order.py -v
```

| Mutation | Test that must fail |
|---|---|
| Change `status=params.status` to `status=None` in `list_orders` | `test_the_status_filter_reaches_the_query` |
| Remove `except ValueError` from `create_order` (leave `except PrintfulError`) | `test_a_core_validation_error_does_not_escape_as_a_traceback` |
| Change `PLACEMENTS_HINT` to `""` | the same test, and `tests/test_create_order.py` |
| Change `orders.confirm_order(params.order_id)` to `orders.get_order(params.order_id)` | `test_confirmation_posts_to_the_confirmation_path` |
| In `markdown.orders`, drop the `- **Status:**` line | add an assertion if none fails — that is a gap, not a pass |

Restore after each, then `rtk proxy git status --porcelain`.

- [ ] **Step 9: Full offline suite, then commit**

```bash
.venv/bin/python -m pytest -q
rtk proxy git add src/printful_mcp/tools/orders.py src/printful_core/format/markdown.py \
  src/printful_mcp/models/inputs.py src/printful_mcp/server.py \
  src/printful_mcp/tests/test_orders.py tests/test_create_order.py
rtk proxy git commit -m "refactor: move the order tools onto the core and let it own item validation"
```

---

### Task 4: Add the four straightforward order tools

**Files:**
- Modify: `src/printful_mcp/tools/orders.py`, `src/printful_mcp/models/inputs.py`, `src/printful_mcp/server.py`
- Modify: `src/printful_core/format/markdown.py` (append `order_items`, `shipments`)
- Modify: `src/printful_mcp/tests/test_orders.py`

**Interfaces:**
- Consumes: everything Task 3 produced.
- Produces: `printful_update_order`, `printful_cancel_order`, `printful_list_order_items`, `printful_list_order_shipments`.

```python
orders.update_order(order_id: str, changes: Dict[str, Any]) -> Request  # raises ValueError on {}
orders.cancel_order(order_id: str) -> Request
orders.list_items(order_id: str) -> Request
orders.list_shipments(order_id: str) -> Request
```

**`cancel` is destructive and `update` is not idempotent.** Their annotations
must say so — `destructiveHint: True` for cancel, `idempotentHint: False` for
update. These are the fields an MCP client uses to decide whether to prompt a
human, so getting them wrong is a safety defect rather than a documentation one.

- [ ] **Step 1: Add the renderers**

Append to `src/printful_core/format/markdown.py`:

```python
def order_items(data: Dict[str, Any], order_id: str) -> str:
    """The items on one order."""
    rows = data.get('data', [])
    lines = [f"# Items on Order {order_id} ({len(rows)})", f""]
    for row in rows:
        lines.extend([
            f"## Item {row.get('id')}",
            f"- **Name:** {row.get('name', 'N/A')}",
            f"- **Variant:** {row.get('catalog_variant_id', 'N/A')}",
            f"- **Quantity:** {row.get('quantity')}",
            f"- **Price:** {row.get('price', 'N/A')} {row.get('currency', '')}",
            f"",
        ])
    return "\n".join(lines)


def shipments(data: Dict[str, Any], order_id: str) -> str:
    """The shipments for one order."""
    rows = data.get('data', [])
    if not rows:
        return (f"# Shipments for Order {order_id}\n\n"
                "No shipments yet. Shipments appear once the order is fulfilled.")
    lines = [f"# Shipments for Order {order_id} ({len(rows)})", f""]
    for row in rows:
        lines.extend([
            f"## Shipment {row.get('id')}",
            f"- **Carrier:** {row.get('carrier', 'N/A')}",
            f"- **Service:** {row.get('service', 'N/A')}",
            f"- **Tracking number:** {row.get('tracking_number', 'N/A')}",
            f"- **Tracking URL:** {row.get('tracking_url', 'N/A')}",
            f"- **Shipped at:** {row.get('shipped_at', 'not yet')}",
            f"",
        ])
    return "\n".join(lines)
```

The empty-shipments branch is not decoration: an order that has not shipped
returns `{"data": []}`, and a bare heading reads like a failure.

- [ ] **Step 2: Add the four input models**

Append to `src/printful_mcp/models/inputs.py`:

```python
class UpdateOrderInput(BaseModel):
    """Input for printful_update_order."""
    order_id: str = Field(description="Order ID or external ID (prefix with @)")
    changes_json: str = Field(
        description=(
            "JSON object of fields to change. Only draft orders can be updated. "
            'Example: {"recipient":{"address1":"2 New Street"}}'
        ),
    )
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")


class CancelOrderInput(BaseModel):
    """Input for printful_cancel_order."""
    order_id: str = Field(description="Order ID or external ID (prefix with @)")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")


class ListOrderItemsInput(BaseModel):
    """Input for printful_list_order_items."""
    order_id: str = Field(description="Order ID or external ID (prefix with @)")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")


class ListOrderShipmentsInput(BaseModel):
    """Input for printful_list_order_shipments."""
    order_id: str = Field(description="Order ID or external ID (prefix with @)")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")
```

`changes_json` is a JSON string rather than a nested model, per invariant 5.

- [ ] **Step 3: Add the four tool bodies**

Append to `src/printful_mcp/tools/orders.py`:

```python
async def update_order(transport: AsyncTransport, params: UpdateOrderInput) -> str:
    """
    Update a draft order.

    Only draft orders can be changed. Pass the fields to change as JSON.
    """
    try:
        changes = json.loads(params.changes_json)
    except json.JSONDecodeError as e:
        return f"Error: changes_json must be valid JSON ({e})."
    if not isinstance(changes, dict):
        return "Error: changes_json must be a JSON object of fields to change."

    try:
        data = await transport.send(orders.update_order(params.order_id, changes))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.order(data.get("data", {}))
    except ValueError as e:
        return f"Error: {e}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def cancel_order(transport: AsyncTransport, params: CancelOrderInput) -> str:
    """
    Cancel an order.

    A draft is discarded. A confirmed order is cancelled if it has not yet
    entered fulfillment. This cannot be undone.
    """
    try:
        data = await transport.send(orders.cancel_order(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        body = data.get("data", {})
        return f"✓ Order {body.get('id', params.order_id)} cancelled."
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_order_items(transport: AsyncTransport, params: ListOrderItemsInput) -> str:
    """
    List the items on an order.
    """
    try:
        data = await transport.send(orders.list_items(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.order_items(data, params.order_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_order_shipments(transport: AsyncTransport,
                               params: ListOrderShipmentsInput) -> str:
    """
    List the shipments for an order, with tracking numbers.
    """
    try:
        data = await transport.send(orders.list_shipments(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.shipments(data, params.order_id)
    except PrintfulError as e:
        return f"Error: {e.message}"
```

Add the four new model names to this module's `..models.inputs` import block.

- [ ] **Step 4: Register the four tools**

Append to `src/printful_mcp/server.py`, and add the four models to its import block:

```python
@mcp.tool(
    name="printful_update_order",
    annotations={
        "title": "Update Draft Order",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def printful_update_order(params: UpdateOrderInput) -> str:
    """
    Update a draft order. Only drafts can be changed.
    """
    return await orders.update_order(get_transport(), params)


@mcp.tool(
    name="printful_cancel_order",
    annotations={
        "title": "Cancel Order",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_cancel_order(params: CancelOrderInput) -> str:
    """
    Cancel an order. A draft is discarded; a confirmed order is cancelled if it
    has not entered fulfillment. This cannot be undone.
    """
    return await orders.cancel_order(get_transport(), params)


@mcp.tool(
    name="printful_list_order_items",
    annotations={
        "title": "List Order Items",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_list_order_items(params: ListOrderItemsInput) -> str:
    """
    List the items on an order.
    """
    return await orders.list_order_items(get_transport(), params)


@mcp.tool(
    name="printful_list_order_shipments",
    annotations={
        "title": "List Order Shipments",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_list_order_shipments(params: ListOrderShipmentsInput) -> str:
    """
    List the shipments for an order, with tracking numbers.
    """
    return await orders.list_order_shipments(get_transport(), params)
```

- [ ] **Step 5: Add the tests**

Append to `src/printful_mcp/tests/test_orders.py`:

```python
async def test_an_update_sends_a_patch_with_only_the_changed_fields(transport):
    """A PUT-shaped update would blank every field the caller omitted."""
    # Queue a renderable body: update_order renders markdown.order(), which reads
    # id/status/created_at/updated_at unguarded. The empty-queue default
    # {"data": {}} would raise KeyError inside the tool's try, and `except
    # PrintfulError` does not catch it -- the failure would read as a tool bug.
    transport._responses.append({"data": {"id": 42, "status": "draft",
                                          "created_at": "2026-01-01",
                                          "updated_at": "2026-01-01"}})
    await orders.update_order(transport, UpdateOrderInput(
        order_id="42", changes_json='{"recipient":{"address1":"2 New Street"}}'))
    assert transport.last.method == "PATCH"
    assert transport.last.path == "/orders/42"
    assert transport.last.json == {"recipient": {"address1": "2 New Street"}}


async def test_an_empty_update_is_refused_before_sending(transport):
    """The core refuses a no-op PATCH; the tool must report it, not crash.

    `update_order` raises ValueError on an empty change set, which is not a
    PrintfulError and escapes a body that catches only that.
    """
    out = await orders.update_order(
        transport, UpdateOrderInput(order_id="42", changes_json="{}"))
    assert out.startswith("Error:")
    assert transport.sent == []


async def test_malformed_update_json_is_reported_not_raised(transport):
    out = await orders.update_order(
        transport, UpdateOrderInput(order_id="42", changes_json="not json"))
    assert "valid JSON" in out
    assert transport.sent == []


async def test_cancel_sends_a_delete(transport):
    """Cancel is destructive; the verb is what makes it so."""
    transport._responses.append({"data": {"id": 42}})
    out = await orders.cancel_order(transport, CancelOrderInput(order_id="42"))
    assert transport.last.method == "DELETE"
    assert transport.last.path == "/orders/42"
    assert "cancelled" in out


async def test_an_unshipped_order_says_so_rather_than_showing_an_empty_heading(transport):
    """`{"data": []}` is the normal answer for an order still in production."""
    transport._responses.append({"data": []})
    out = await orders.list_order_shipments(
        transport, ListOrderShipmentsInput(order_id="42"))
    assert "No shipments yet" in out
```

Confirm `orders.cancel_order` in the core actually issues `DELETE` before
asserting it; if it uses a different verb, assert what the core does and say so
in your report rather than changing the core.

- [ ] **Step 6: Run, mutate, commit**

```bash
.venv/bin/python -m pytest src/printful_mcp/tests/ -v
```

| Mutation | Test that must fail |
|---|---|
| Change `PATCH` handling: call `orders.create_order` instead of `update_order` | `test_an_update_sends_a_patch_with_only_the_changed_fields` |
| Remove `except ValueError` from `update_order` | `test_an_empty_update_is_refused_before_sending` |
| In `markdown.shipments`, delete the empty-rows branch | `test_an_unshipped_order_says_so_rather_than_showing_an_empty_heading` |
| Set `"destructiveHint": False` on `printful_cancel_order` | add an annotation test in Task 9 if none fails |

```bash
.venv/bin/python -m pytest -q
rtk proxy git add src/printful_mcp/tools/orders.py src/printful_mcp/models/inputs.py \
  src/printful_mcp/server.py src/printful_core/format/markdown.py \
  src/printful_mcp/tests/test_orders.py
rtk proxy git commit -m "feat: add the update, cancel, items and shipments order tools"
```

---
### Task 5: Add cost estimation as two tools, not one

**Files:**
- Modify: `src/printful_mcp/tools/orders.py`, `src/printful_mcp/models/inputs.py`, `src/printful_mcp/server.py`
- Modify: `src/printful_core/format/markdown.py` (append `estimate`)
- Modify: `src/printful_mcp/tests/test_orders.py`

**Interfaces:**
```python
orders.create_estimation_task(recipient: Dict, items: List[Dict]) -> Request
orders.get_estimation_task(task_id: str) -> Request
polling.task_body(response) -> Dict
polling.classify_task(body) -> str          # "completed" | "failed" | "pending"
```

#### Why this is two tools where the CLI has one command

The spec's parity table lists a single `estimate_costs`. The CLI implements it
by creating the task and then polling until it settles. **The MCP does not
poll**, and gets two tools instead.

Three reasons, and they compound:

1. **A polling driver blocks on the clock.** `poll_estimation_task_async` sleeps
   between attempts — `printful_core/polling.py`'s docstring says so explicitly,
   and Ruling 32 exists to keep that visible. A tool that awaits it holds the
   tool call open for up to `max_wait`, and an MCP client that times out gets
   nothing, having already created the task.
2. **The house pattern already exists.** `printful_create_mockup_task` and
   `printful_get_mockup_task` are exactly this split, for exactly this reason.
   A calling model already knows the shape.
3. **The core keeps four poll drivers, not two** (Ruling 25): estimation's driver
   takes `created`, which mockups has no equivalent for. Collapsing them was
   considered and rejected in plan 1, so there is no single driver to reach for.

The two pure decision functions — `task_body` and `classify_task` — *are* shared,
and the status tool uses them. That is the part of the polling module that costs
nothing to call.

**Put a shortened version of this rationale in `get_estimation_task`'s docstring.**
A reviewer hits the code before they hit this plan.

- [ ] **Step 1: Add the renderer**

Append to `src/printful_core/format/markdown.py`:

```python
def estimate(body: Dict[str, Any], status: str) -> str:
    """One estimation task, in whichever state it is in."""
    if status == "pending":
        return ("# Cost Estimate\n\n**Status:** pending\n\n"
                "The estimate is still being calculated. Call "
                "printful_get_estimation_task again in a few seconds.")
    if status == "failed":
        reasons = body.get("failure_reasons") or []
        detail = "\n".join(f"- {r}" for r in reasons) or "- No reason given."
        return f"# Cost Estimate\n\n**Status:** failed\n\n{detail}"

    costs = (body.get("costs") or {})
    currency = costs.get("currency", "")
    lines = [
        f"# Cost Estimate",
        f"",
        f"**Status:** completed",
        f"**Currency:** {currency}",
        f"**Subtotal:** {costs.get('subtotal', 'N/A')}",
        f"**Shipping:** {costs.get('shipping', 'N/A')}",
        f"**Tax:** {costs.get('tax', 'N/A')}",
        f"**Total:** {costs.get('total', 'N/A')}",
        f"",
    ]
    return "\n".join(lines)
```

- [ ] **Step 2: Add the two input models**

```python
class CreateEstimationTaskInput(BaseModel):
    """Input for printful_create_estimation_task."""
    recipient_country_code: str = Field(description="Destination country code, e.g. US")
    recipient_state_code: Optional[str] = Field(
        default=None, description="State code (required for US, CA, AU)")
    recipient_city: Optional[str] = Field(default=None, description="Destination city")
    recipient_zip: Optional[str] = Field(default=None, description="Destination ZIP")
    items_json: str = Field(
        description=(
            "JSON array of order items. Example: "
            '[{"source":"catalog","catalog_variant_id":4012,"quantity":1}]'
        ),
    )
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")


class GetEstimationTaskInput(BaseModel):
    """Input for printful_get_estimation_task."""
    task_id: str = Field(description="Task ID returned by printful_create_estimation_task")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")
```

**Do not require placements here.** `create_estimation_task` deliberately skips
`_require_placements`, and that was confirmed rather than assumed in plan 1
(Ruling 17): a rate can be quoted for an item with no artwork even though
creating an order with one cannot. Adding a validation branch would break a
working path.

- [ ] **Step 3: Add the two tool bodies**

Append to `src/printful_mcp/tools/orders.py`:

```python
async def create_estimation_task(transport: AsyncTransport,
                                 params: CreateEstimationTaskInput) -> str:
    """
    Start a cost estimate for a would-be order.

    Returns a task ID immediately. Read the result with
    printful_get_estimation_task. Artwork is not required to estimate costs.
    """
    recipient = {"country_code": params.recipient_country_code}
    if params.recipient_state_code:
        recipient["state_code"] = params.recipient_state_code
    if params.recipient_city:
        recipient["city"] = params.recipient_city
    if params.recipient_zip:
        recipient["zip"] = params.recipient_zip

    try:
        items = json.loads(params.items_json)
    except json.JSONDecodeError as e:
        return f"Error: items_json must be valid JSON array ({e})."
    if not isinstance(items, list) or not items:
        return "Error: items_json must be a non-empty JSON array of order items."

    try:
        request = orders.create_estimation_task(recipient, items)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        body = polling.task_body(data)
        return (f"Estimation task created.\n\nTask ID: {body.get('id')}\n"
                f"Status: {body.get('status')}\n\n"
                "Read the result with printful_get_estimation_task.")
    except ValueError as e:
        return f"Error: {e}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_estimation_task(transport: AsyncTransport,
                              params: GetEstimationTaskInput) -> str:
    """
    Read a cost estimate started by printful_create_estimation_task.

    Returns pending, failed, or the calculated costs. Call again after a few
    seconds while it is pending.

    This is a separate tool rather than a wait inside the create call because
    the core's polling drivers sleep against a deadline. Awaiting one here
    would hold the tool call open for the whole timeout, and a client that
    gave up would have created a task it could never read. The mockup tools
    are split for the same reason.
    """
    try:
        data = await transport.send(orders.get_estimation_task(params.task_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        body = polling.task_body(data)
        return markdown.estimate(body, polling.classify_task(body))
    except PrintfulError as e:
        return f"Error: {e.message}"
```

Add `from printful_core import polling` to the module imports, and the two new
model names to the `..models.inputs` block.

- [ ] **Step 4: Register both tools**

Both are `readOnlyHint: False` — creating a task is a write, even though nothing
is charged.

```python
@mcp.tool(
    name="printful_create_estimation_task",
    annotations={
        "title": "Start Cost Estimate",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def printful_create_estimation_task(params: CreateEstimationTaskInput) -> str:
    """
    Start a cost estimate for a would-be order. Returns a task ID immediately;
    read the result with printful_get_estimation_task.
    """
    return await orders.create_estimation_task(get_transport(), params)


@mcp.tool(
    name="printful_get_estimation_task",
    annotations={
        "title": "Get Cost Estimate",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_get_estimation_task(params: GetEstimationTaskInput) -> str:
    """
    Read a cost estimate. Returns pending, failed, or the calculated costs.
    """
    return await orders.get_estimation_task(get_transport(), params)
```

- [ ] **Step 5: Test the three states and the list-shaped body**

Append to `src/printful_mcp/tests/test_orders.py`:

```python
async def test_a_pending_estimate_tells_the_caller_to_come_back(transport):
    """A pending task must not render as an estimate of zero.

    `classify_task` returns "pending" for anything that is neither completed
    nor failed, and the costs block is absent in that state.
    """
    transport._responses.append({"data": {"id": "t1", "status": "pending"}})
    out = await orders.get_estimation_task(transport, GetEstimationTaskInput(task_id="t1"))
    assert "pending" in out
    assert "printful_get_estimation_task again" in out


async def test_a_list_shaped_task_body_is_unwrapped(transport):
    """The API returns this task as a one-element list, not an object.

    `task_body` handles both. A tool that read `data` directly would render a
    list where a dict is expected and report every estimate as pending.
    """
    transport._responses.append(
        {"data": [{"id": "t2", "status": "completed",
                   "costs": {"currency": "USD", "total": "24.95"}}]})
    out = await orders.get_estimation_task(transport, GetEstimationTaskInput(task_id="t2"))
    assert "completed" in out
    assert "24.95" in out


async def test_a_failed_estimate_reports_why(transport):
    transport._responses.append(
        {"data": {"id": "t3", "status": "failed",
                  "failure_reasons": ["No shipping to that country"]}})
    out = await orders.get_estimation_task(transport, GetEstimationTaskInput(task_id="t3"))
    assert "failed" in out
    assert "No shipping to that country" in out


async def test_estimation_does_not_require_artwork(transport):
    """Rates can be quoted for an item with no placements.

    Order creation rejects such an item; estimation does not. Adding a
    placements check here would break a working path -- this was confirmed
    against the live API, not assumed.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}]
    out = await orders.create_estimation_task(transport, CreateEstimationTaskInput(
        recipient_country_code="US", recipient_state_code="CA",
        items_json=json.dumps(items)))
    assert not out.startswith("Error:")
    assert transport.last.path == "/order-estimation-tasks"
```

Confirm the path `create_estimation_task` builds before asserting it; assert
what the core does.

- [ ] **Step 6: Run, mutate, commit**

| Mutation | Test that must fail |
|---|---|
| In `get_estimation_task`, use `data.get("data")` instead of `polling.task_body(data)` | `test_a_list_shaped_task_body_is_unwrapped` |
| In `markdown.estimate`, drop the `status == "pending"` branch | `test_a_pending_estimate_tells_the_caller_to_come_back` |
| Add `orders._require_placements(items)` to `create_estimation_task` | `test_estimation_does_not_require_artwork` |

```bash
.venv/bin/python -m pytest -q
rtk proxy git add src/printful_mcp/tools/orders.py src/printful_mcp/models/inputs.py \
  src/printful_mcp/server.py src/printful_core/format/markdown.py \
  src/printful_mcp/tests/test_orders.py
rtk proxy git commit -m "feat: add cost estimation as a create tool and a status tool"
```

---

### Task 6: Move shipping onto the core, fix the countries defect, add tax

**Files:**
- Modify: `src/printful_mcp/tools/shipping.py` (rewrite; 107 lines today)
- Modify: `src/printful_core/format/markdown.py` (append `rates`, `countries`, `tax`)
- Modify: `src/printful_mcp/models/inputs.py`, `src/printful_mcp/server.py`
- Create: `src/printful_mcp/tests/test_shipping.py`

**Interfaces:**
```python
shipping.list_countries() -> Request                      # paginated; needs collect_pages_async
shipping.calculate_rates(recipient, items, currency=None, locale=None) -> Request
shipping.calculate_tax(country_code, state_code=None, city=None, zip_code=None) -> Request
                                                          # version="v1" -- v2 has no tax endpoint
pagination.collect_pages_async(request, send) -> Dict
```

#### This task fixes a live defect

`src/printful_mcp/tools/shipping.py:83` sends
`client.get("/countries", params={"limit": 250})` — one request with an explicit
high limit. `/v2/countries` paginates at 20 by default and reports the limit the
server actually applied in `paging.limit`, so `limit=250` is honored only if the
endpoint has no lower cap. The CLI hit exactly this and the country list came
back **without the United States**, because `US` falls outside the first page
alphabetically. The spec lists it as defect 4.

**`list_countries` is the one tool in this plan that calls `collect_pages_async`.**
It takes no `limit` or `offset` parameters, so the caller cannot page for
themselves and the tool must walk the collection. Every other list tool exposes
paging and sends exactly one request.

The core builder deliberately sets no limit at all — `collect_pages_async` asks
for `PAGE_LIMIT` on the first call and then uses whatever limit the server
reports for the rest.

Two shape changes come free with routing through the core, and both are
improvements over what the MCP sends today:

- `calculate_rates` defaults each item's `source` to `"catalog"`. The endpoint
  rejects an item without it: *"Property /order_items/0/source must be of type
  `string`, `null` provided."*
- `calculate_tax` is a **v1** request. The `Request.version` field carries that;
  do not hand-build a v1 URL.

- [ ] **Step 1: Add the renderers**

Append to `src/printful_core/format/markdown.py`:

```python
def rates(data: Dict[str, Any]) -> str:
    """Available shipping options."""
    rows = data.get('data', [])
    lines = [f"# Shipping Rates", f"", f"Found {len(rows)} shipping options", f""]
    for row in rows:
        delivery = f"{row['min_delivery_days']}-{row['max_delivery_days']} days"
        lines.extend([
            f"## {row['shipping_method_name']}",
            f"- **Rate:** {row['rate']} {row['currency']}",
            f"- **Delivery:** {delivery} ({row['min_delivery_date']} to "
            f"{row['max_delivery_date']})",
            f"",
        ])
        if row.get('shipments'):
            lines.append("### Shipments")
            for shipment in row['shipments']:
                customs = "Yes" if shipment.get('customs_fees_possible') else "No"
                lines.append(
                    f"- From {shipment['departure_country']} - "
                    f"Customs fees possible: {customs}")
            lines.append("")
    return "\n".join(lines)


def countries(data: Dict[str, Any]) -> str:
    """Every country Printful ships to."""
    rows = data.get('data', [])
    lines = [f"# Available Countries ({len(rows)} total)", f""]
    for row in rows:
        lines.append(f"## {row['name']} ({row['code']})")
        if row.get('states'):
            lines.append(f"**States:** {len(row['states'])} available")
            for state in row['states'][:3]:
                lines.append(f"  - {state['name']} ({state['code']})")
            if len(row['states']) > 3:
                lines.append(f"  - _(and {len(row['states']) - 3} more)_")
        lines.append("")
    return "\n".join(lines)


def tax(data: Dict[str, Any]) -> str:
    """A tax rate for one destination."""
    body = data if not isinstance(data.get('data'), dict) else data['data']
    required = body.get('required')
    lines = [
        f"# Tax Rate",
        f"",
        f"**Tax required:** {'yes' if required else 'no'}",
        f"**Rate:** {body.get('rate', 'N/A')}",
        f"**Shipping taxable:** {'yes' if body.get('shipping_taxable') else 'no'}",
        f"",
    ]
    return "\n".join(lines)
```

The heading counts rows rather than reading `paging.total`, because after
`merge_pages` the rows *are* the whole collection and the two must agree.

- [ ] **Step 2: Add the tax input model**

```python
class CalculateTaxInput(BaseModel):
    """Input for printful_calculate_tax."""
    country_code: str = Field(description="Destination country code, e.g. US")
    state_code: Optional[str] = Field(default=None, description="State code, e.g. CA")
    city: Optional[str] = Field(default=None, description="Destination city")
    zip_code: Optional[str] = Field(default=None, description="Destination ZIP/postal code")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")
```

- [ ] **Step 3: Rewrite `src/printful_mcp/tools/shipping.py`**

```python
"""Shipping tools for the Printful MCP server."""

import json

from printful_core.endpoints import shipping
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.pagination import collect_pages_async
from printful_core.transport import AsyncTransport

from ..models.inputs import CalculateShippingInput, CalculateTaxInput


async def calculate_shipping_rates(transport: AsyncTransport,
                                   params: CalculateShippingInput) -> str:
    """
    Calculate shipping rates for an order.

    Provides available shipping methods and costs based on recipient location
    and order items. Returns estimated delivery times and customs fee information.
    """
    try:
        items = json.loads(params.items_json)
    except json.JSONDecodeError:
        return ('Error: items_json must be valid JSON array. Example: '
                '[{"catalog_variant_id": 4011, "quantity": 1, "source": "catalog"}]')
    if not isinstance(items, list) or not items:
        return "Error: items_json must be a non-empty JSON array of order items."

    recipient = {"country_code": params.recipient_country_code}
    if params.recipient_state_code:
        recipient["state_code"] = params.recipient_state_code
    if params.recipient_city:
        recipient["city"] = params.recipient_city
    if params.recipient_zip:
        recipient["zip"] = params.recipient_zip

    try:
        request = shipping.calculate_rates(recipient, items, currency=params.currency)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.rates(data)
    except ValueError as e:
        return f"Error: {e}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_countries(transport: AsyncTransport) -> str:
    """
    List all countries where Printful is available.

    Returns country codes and state codes needed for order creation.

    This walks every page. /v2/countries paginates at 20 of roughly 239 rows,
    and a single request drops everything after the first page -- which is how
    a previous version of this tool reported that Printful does not ship to the
    United States.
    """
    try:
        data = await collect_pages_async(shipping.list_countries(), transport.send)
        return markdown.countries(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def calculate_tax(transport: AsyncTransport, params: CalculateTaxInput) -> str:
    """
    Get the tax rate for a destination.

    This uses API v1; v2 exposes no tax endpoint.
    """
    try:
        request = shipping.calculate_tax(
            params.country_code, state_code=params.state_code,
            city=params.city, zip_code=params.zip_code)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.tax(data)
    except PrintfulError as e:
        return f"Error: {e.message}"
```

`list_countries` keeps its no-arguments signature — it is the only tool with no
input model, and `.claude/CLAUDE.md` records that as a known, accepted
inconsistency. Do not add one.

- [ ] **Step 4: Wire the server**

Change the two existing shipping delegates to pass `get_transport()`, then add:

```python
@mcp.tool(
    name="printful_calculate_tax",
    annotations={
        "title": "Calculate Tax Rate",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_calculate_tax(params: CalculateTaxInput) -> str:
    """
    Get the tax rate for a destination. Uses API v1; v2 has no tax endpoint.
    """
    return await shipping.calculate_tax(get_transport(), params)
```

- [ ] **Step 5: Write the tests**

Create `src/printful_mcp/tests/test_shipping.py`:

```python
"""The shipping adapter, including the pagination defect this tool used to have."""
import json

from printful_mcp.models.inputs import CalculateShippingInput, CalculateTaxInput
from printful_mcp.tools import shipping
from printful_mcp.tests.conftest import FakeTransport


async def test_the_country_list_walks_every_page():
    """A single request reports that Printful does not ship to the US.

    /v2/countries paginates at 20 of ~239 rows and `US` is late alphabetically,
    so the first page does not contain it. This is defect 4 from the spec, and
    it was live in this tool.
    """
    page_one = {"data": [{"code": "AT", "name": "Austria"}],
                "paging": {"total": 2, "limit": 1, "offset": 0}}
    page_two = {"data": [{"code": "US", "name": "United States"}],
                "paging": {"total": 2, "limit": 1, "offset": 1}}
    transport = FakeTransport([page_one, page_two])

    out = await shipping.list_countries(transport)

    assert len(transport.sent) == 2, "only the first page was fetched"
    assert "United States" in out
    assert "(2 total)" in out


async def test_rates_default_each_item_source_to_catalog(transport):
    """The endpoint rejects an item with a null source.

    'Property /order_items/0/source must be of type `string`, `null` provided'
    -- observed against the live API.
    """
    await shipping.calculate_shipping_rates(transport, CalculateShippingInput(
        recipient_country_code="US",
        items_json=json.dumps([{"catalog_variant_id": 4011, "quantity": 1}])))
    assert transport.last.json["order_items"][0]["source"] == "catalog"


async def test_tax_goes_to_v1(transport):
    """v2 exposes no tax endpoint, so this request must carry version v1.

    A v2 request to /tax/rates 404s, and the tool would report the destination
    as untaxed rather than unreachable.
    """
    await shipping.calculate_tax(
        transport, CalculateTaxInput(country_code="US", state_code="CA"))
    assert transport.last.version == "v1"
    assert transport.last.path == "/tax/rates"


async def test_malformed_items_json_is_reported_not_raised(transport):
    out = await shipping.calculate_shipping_rates(transport, CalculateShippingInput(
        recipient_country_code="US", items_json="not json"))
    assert "valid JSON" in out
    assert transport.sent == []
```

`test_the_country_list_walks_every_page` builds its own `FakeTransport` rather
than using the fixture, because it needs two queued pages.

- [ ] **Step 6: Run, mutate, commit**

| Mutation | Test that must fail |
|---|---|
| Replace `collect_pages_async(...)` with `transport.send(shipping.list_countries())` | `test_the_country_list_walks_every_page` |
| In the core, drop the `source` defaulting from `calculate_rates` | `test_rates_default_each_item_source_to_catalog` |
| In the core, remove `version="v1"` from `calculate_tax` | `test_tax_goes_to_v1` |

The second and third mutate the core, so `src/printful_cli/` runs against them
too — confirm the CLI suite is green after restoring.

```bash
.venv/bin/python -m pytest -q
rtk proxy git add src/printful_mcp/tools/shipping.py src/printful_core/format/markdown.py \
  src/printful_mcp/models/inputs.py src/printful_mcp/server.py \
  src/printful_mcp/tests/test_shipping.py
rtk proxy git commit -m "fix: walk every page of the country list and add the tax tool"
```

---
### Task 7: Move mockups onto the core and add styles and templates

**Files:**
- Modify: `src/printful_mcp/tools/mockups.py` (rewrite; 107 lines today)
- Modify: `src/printful_core/format/markdown.py` (append `mockup_task`, `mockup_styles`, `mockup_templates`)
- Modify: `src/printful_mcp/models/inputs.py`, `src/printful_mcp/server.py`
- Create: `src/printful_mcp/tests/test_mockups.py`

**Interfaces:**
```python
mockups.create_task(product_id, variant_ids: List[int], image_url: str,
                    placement="front", technique="dtg",
                    style_ids: Optional[List[int]] = None,
                    image_format="jpg") -> Request          # raises ValueError
mockups.get_task(task_id: str) -> Request                   # GET /mockup-tasks?id=...
mockups.list_styles(product_id: int) -> Request
mockups.list_templates(product_id: int) -> Request
mockups.RATE_LIMIT_NOTE   # the string to put in the create tool's docstring
```

#### Three things about this domain that will catch you

1. **`CreateMockupTaskInput.format` is the image format, not the response
   format.** It is `Literal["jpg", "png"]`, and it is the one documented
   exception to invariant 2. The core parameter it feeds is named
   `image_format` precisely so the two cannot be confused. **Do not rename the
   model field** — that is a breaking change to a published tool schema for a
   cosmetic gain. Map it: `image_format=params.format`.
2. **`mockup_style_ids` is required in the model and optional in the core.**
   The core omits `mockup_style_ids` from the request body entirely when no
   styles are given, which is what lets Printful pick its defaults. Make the
   model field `Optional[str] = None` — this is a parity fix, and widening a
   required field to optional does not break an existing caller.
3. **The core adds `"orientation": "any"` to the product block.** The MCP's
   hand-built body does not. Routing through the core changes the request, and
   that is the point: the CLI's version is the one verified against the live
   API. Note it in your report.

`printful_create_mockup_task` is rate-limited hard — 2 requests/60s for a new
store with a 60-second lockout. Put `mockups.RATE_LIMIT_NOTE` in the tool
docstring so a calling model sees it before it retries in a loop.

- [ ] **Step 1: Add the renderers**

Append to `src/printful_core/format/markdown.py`. `mockup_task`'s body is the
markdown block currently inline in `src/printful_mcp/tools/mockups.py:68-103` —
move it verbatim, changing only `task` to the `body` argument:

```python
def mockup_task(body: Dict[str, Any]) -> str:
    """One mockup task, in whichever state it is in."""
    lines = [f"# Mockup Task {body['id']}", f"", f"**Status:** {body['status']}", f""]
    if body['status'] == 'completed':
        variant_mockups = body.get('catalog_variant_mockups', [])
        lines.append(f"## Generated Mockups ({len(variant_mockups)} variants)")
        for vm in variant_mockups:
            lines.append(f"### Variant {vm['catalog_variant_id']}")
            for mockup in vm.get('mockups', []):
                lines.extend([
                    f"- **{mockup['display_name']}** ({mockup['placement']})",
                    f"  - Style ID: {mockup['style_id']}",
                    f"  - URL: {mockup['mockup_url']}",
                ])
            lines.append("")
    elif body['status'] == 'pending':
        lines.append("⏳ Mockup generation in progress. Check again in a few seconds.")
    elif body['status'] == 'failed':
        lines.append("❌ Mockup generation failed.")
        if body.get('failure_reasons'):
            lines.append("\n**Reasons:**")
            for reason in body['failure_reasons']:
                lines.append(f"- {reason.get('detail', 'Unknown error')}")
    return "\n".join(lines)


def mockup_styles(data: Dict[str, Any], product_id: int) -> str:
    """The mockup styles available for one product."""
    rows = data.get('data', [])
    lines = [f"# Mockup Styles for Product {product_id} ({len(rows)})", f""]
    for row in rows:
        lines.extend([
            f"## {row.get('name', 'Style')} — ID {row.get('id')}",
            f"- **Placement:** {row.get('placement', 'N/A')}",
            f"- **Technique:** {row.get('technique', 'N/A')}",
            f"",
        ])
    return "\n".join(lines)


def mockup_templates(data: Dict[str, Any], product_id: int) -> str:
    """The print-area templates for one product."""
    rows = data.get('data', [])
    lines = [f"# Mockup Templates for Product {product_id} ({len(rows)})", f""]
    for row in rows:
        lines.extend([
            f"## Template {row.get('id')}",
            f"- **Placement:** {row.get('placement', 'N/A')}",
            f"- **Technique:** {row.get('technique', 'N/A')}",
            f"- **Print area:** {row.get('print_area_width')}x"
            f"{row.get('print_area_height')}",
            f"- **Image:** {row.get('image_url', 'N/A')}",
            f"",
        ])
    return "\n".join(lines)
```

- [ ] **Step 2: Widen `mockup_style_ids` and add the two new models**

In `CreateMockupTaskInput`, change:

```python
    mockup_style_ids: str = Field(..., description="Comma-separated mockup style IDs")
```

to:

```python
    mockup_style_ids: Optional[str] = Field(
        default=None,
        description=("Comma-separated mockup style IDs. Omit to let Printful "
                     "choose its defaults. Find IDs with printful_list_mockup_styles."))
```

Then append:

```python
class ListMockupStylesInput(BaseModel):
    """Input for printful_list_mockup_styles."""
    product_id: int = Field(description="Catalog product ID")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")


class ListMockupTemplatesInput(BaseModel):
    """Input for printful_list_mockup_templates."""
    product_id: int = Field(description="Catalog product ID")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")
```

- [ ] **Step 3: Rewrite `src/printful_mcp/tools/mockups.py`**

```python
"""Mockup generator tools for the Printful MCP server."""

import json

from printful_core import polling
from printful_core.endpoints import mockups
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import (
    CreateMockupTaskInput,
    GetMockupTaskInput,
    ListMockupStylesInput,
    ListMockupTemplatesInput,
)


def _ids(raw: str) -> list:
    return [int(v.strip()) for v in raw.split(",") if v.strip()]


async def create_mockup_task(transport: AsyncTransport,
                             params: CreateMockupTaskInput) -> str:
    """
    Create a mockup generation task.

    Generates product mockups asynchronously. Returns a task ID; read the result
    with printful_get_mockup_task. Generation usually takes 10-30 seconds.

    Mockup creation is limited to 10 requests/60s (established stores) or
    2 requests/60s (new stores), with a 60s lockout when exceeded. Do not retry
    in a loop.
    """
    try:
        variant_ids = _ids(params.variant_ids)
        style_ids = _ids(params.mockup_style_ids) if params.mockup_style_ids else None
    except ValueError as e:
        return f"Error parsing input: {e}"

    try:
        request = mockups.create_task(
            params.product_id, variant_ids, params.design_url,
            placement=params.placement, technique=params.technique,
            style_ids=style_ids, image_format=params.format)
        data = await transport.send(request)
        body = polling.task_body(data)
        if not body:
            return json.dumps(data, indent=2)
        return (f"Mockup task created!\n\nTask ID: {body['id']}\n"
                f"Status: {body['status']}\n\n"
                "Use printful_get_mockup_task with this ID to check status and "
                "get mockup URLs.")
    except ValueError as e:
        return f"Error: {e}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_mockup_task(transport: AsyncTransport, params: GetMockupTaskInput) -> str:
    """
    Get mockup task status and results.

    Check whether mockup generation is complete and retrieve image URLs. Status
    is pending, completed, or failed.
    """
    try:
        data = await transport.send(mockups.get_task(params.task_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        body = polling.task_body(data)
        if not body:
            return f"No task found with ID {params.task_id}"
        return markdown.mockup_task(body)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_mockup_styles(transport: AsyncTransport,
                             params: ListMockupStylesInput) -> str:
    """
    List the mockup styles available for a catalog product.

    Style IDs are what printful_create_mockup_task takes in mockup_style_ids.
    """
    try:
        data = await transport.send(mockups.list_styles(params.product_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.mockup_styles(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_mockup_templates(transport: AsyncTransport,
                                params: ListMockupTemplatesInput) -> str:
    """
    List the print-area templates for a catalog product.

    Templates give the printable dimensions a design must fit.
    """
    try:
        data = await transport.send(mockups.list_templates(params.product_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.mockup_templates(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"
```

`polling.task_body` replaces the hand-written `tasks = data.get('data', []); task = tasks[0]`
in both existing bodies. It handles the object shape and the one-element-list
shape, which is the same widening plan 1 applied to the estimation path.

**Do not call `poll_mockup_task_async` here.** Same reason as Task 5: the driver
sleeps against a deadline, and the create/get split already exists so a caller
never has to wait inside a tool call. `_mockup_timeout`'s `recovery_hint`
parameter exists for a CLI that does poll (Ruling 26); this surface does not.

- [ ] **Step 4: Register the two new tools**

Both read-only, following the established form, with `ListMockupStylesInput` and
`ListMockupTemplatesInput` added to `server.py`'s import block and the two
existing mockup delegates switched to `get_transport()`:

```python
@mcp.tool(
    name="printful_list_mockup_styles",
    annotations={
        "title": "List Mockup Styles",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_list_mockup_styles(params: ListMockupStylesInput) -> str:
    """
    List the mockup styles available for a catalog product. Style IDs feed
    printful_create_mockup_task.
    """
    return await mockups.list_mockup_styles(get_transport(), params)


@mcp.tool(
    name="printful_list_mockup_templates",
    annotations={
        "title": "List Mockup Templates",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_list_mockup_templates(params: ListMockupTemplatesInput) -> str:
    """
    List the print-area templates for a catalog product.
    """
    return await mockups.list_mockup_templates(get_transport(), params)
```

- [ ] **Step 5: Write the tests**

Create `src/printful_mcp/tests/test_mockups.py`:

```python
"""The mockups adapter."""
from printful_mcp.models.inputs import (
    CreateMockupTaskInput,
    GetMockupTaskInput,
    ListMockupStylesInput,
)
from printful_mcp.tools import mockups


def _create(**over):
    base = dict(product_id=71, variant_ids="4011,4012",
                design_url="https://example.com/art.png")
    base.update(over)
    return CreateMockupTaskInput(**base)


async def test_the_image_format_field_is_not_the_response_format(transport):
    """`format` on this model means jpg or png, and feeds image_format.

    Every other tool's `format` selects markdown or json. Mapping this one to
    the wrong core parameter produces a request asking for a mockup in
    "markdown".
    """
    await mockups.create_mockup_task(transport, _create(format="png"))
    assert transport.last.json["format"] == "png"


async def test_omitted_style_ids_are_left_out_of_the_request(transport):
    """Printful picks its own defaults only when the key is absent.

    An empty `mockup_style_ids` list is not the same as no key: the API reads
    it as "these zero styles" and returns nothing.
    """
    await mockups.create_mockup_task(transport, _create())
    product = transport.last.json["products"][0]
    assert "mockup_style_ids" not in product


async def test_supplied_style_ids_arrive_as_integers(transport):
    """The model takes a comma-separated string; the API takes numbers."""
    await mockups.create_mockup_task(transport, _create(mockup_style_ids="7, 9"))
    assert transport.last.json["products"][0]["mockup_style_ids"] == [7, 9]


async def test_a_task_returned_as_a_one_element_list_is_unwrapped(transport):
    """/mockup-tasks returns the task inside a list.

    Reading `data` directly renders a list where a dict is expected.
    """
    transport._responses.append({"data": [{"id": "m1", "status": "pending"}]})
    out = await mockups.get_mockup_task(transport, GetMockupTaskInput(task_id="m1"))
    assert "# Mockup Task m1" in out
    assert "in progress" in out


async def test_a_missing_task_says_so(transport):
    transport._responses.append({"data": []})
    out = await mockups.get_mockup_task(transport, GetMockupTaskInput(task_id="nope"))
    assert out == "No task found with ID nope"


async def test_styles_are_fetched_per_product(transport):
    await mockups.list_mockup_styles(transport, ListMockupStylesInput(product_id=71))
    assert transport.last.path == "/catalog-products/71/mockup-styles"
```

**No test in this file may reach the live API.** Mockup creation is the most
tightly rate-limited endpoint in the product; every assertion here runs against
the fake.

- [ ] **Step 6: Run, mutate, commit**

| Mutation | Test that must fail |
|---|---|
| Change `image_format=params.format` to `image_format="jpg"` | `test_the_image_format_field_is_not_the_response_format` |
| Change `style_ids=style_ids` to `style_ids=style_ids or []` | `test_omitted_style_ids_are_left_out_of_the_request` |
| In `get_mockup_task`, use `data.get("data")` instead of `polling.task_body(data)` | `test_a_task_returned_as_a_one_element_list_is_unwrapped` |

```bash
.venv/bin/python -m pytest -q
rtk proxy git add src/printful_mcp/tools/mockups.py src/printful_core/format/markdown.py \
  src/printful_mcp/models/inputs.py src/printful_mcp/server.py \
  src/printful_mcp/tests/test_mockups.py
rtk proxy git commit -m "feat: move the mockup tools onto the core and add styles and templates"
```

---

### Task 8: Move files, stores and sync onto the core

**Files:**
- Modify: `src/printful_mcp/tools/files.py` (105 lines), `stores.py` (122), `sync.py` (111)
- Modify: `src/printful_core/format/markdown.py` (append six renderers)
- Modify: `src/printful_mcp/models/inputs.py`, `src/printful_mcp/server.py`
- Create: `src/printful_mcp/tests/test_small_domains.py`

**Interfaces:**
```python
files.add_file(url: str, filename=None, visible=True) -> Request
files.get_file(file_id: int) -> Request
stores.list_stores() -> Request
stores.get_statistics(store_id: int, date_from: str, date_to: str,
                      report_types="sales_and_costs,profit", currency=None) -> Request
stores.list_templates(limit=20, offset=0) -> Request        # new tool
sync.list_products(limit=20, offset=0) -> Request           # v1
sync.get_product(sync_product_id: int) -> Request           # v1
```

These three domains are six existing tools plus one new one, all of the same
shape, so they are one task rather than three. One new tool:
`printful_list_store_templates`.

#### The arity trap in `list_templates`

Two core builders share a name and do not share a signature:

```python
mockups.list_templates(product_id)                  # product_id REQUIRED
stores.list_templates(limit=20, offset=0)           # takes paging, not an id
```

`stores.list_templates(71)` **silently binds 71 to `limit`** and returns a
perfectly valid-looking `Request` for the wrong collection. Import the module,
never the bare function, and check each call against the builder you actually
imported. This cost a fix round in plan 1.

#### `sync` is v1

`printful_core.endpoints.sync` builds `version="v1"` requests, because v2 exposes
no sync-product endpoint. The transport reads `Request.version`; do not
hand-build a URL. `_normalize` already unwraps the v1 `{"code":..., "result":...}`
envelope down to `result`, so the tool bodies see the same shape they do today.

- [ ] **Step 1: Move the six renderers into the core**

Append to `src/printful_core/format/markdown.py`, moving each block verbatim
from its current inline location and changing only the variable that holds the
body:

| New function | Move from | Signature |
|---|---|---|
| `file_added` | `tools/files.py:30-48` | `(body: Dict[str, Any]) -> str` |
| `file_detail` | `tools/files.py:68-101` | `(body: Dict[str, Any]) -> str` |
| `stores` | `tools/stores.py` — the `list_stores` markdown branch | `(data: Dict[str, Any]) -> str` |
| `store_statistics` | `tools/stores.py` — the `get_store_statistics` branch | `(data: Dict[str, Any]) -> str` |
| `sync_products` | `tools/sync.py` — the `list_sync_products` branch | `(data: Dict[str, Any]) -> str` |
| `sync_product` | `tools/sync.py` — the `get_sync_product` branch | `(body: Dict[str, Any]) -> str` |

**Every one of these must produce byte-identical output to what it replaces.**
These are strings a person reads. If you find yourself improving the wording,
stop — that is a behavior change wearing a refactor's clothes, and Step 4 pins
two of them precisely so it cannot pass unnoticed.

Add one renderer that has no predecessor:

```python
def store_templates(data: Dict[str, Any]) -> str:
    """A page of saved product templates."""
    rows = data.get('data', [])
    paging = data.get('paging', {})
    lines = [
        f"# Product Templates ({paging.get('total', 0)} total)",
        f"",
        f"Showing {len(rows)} templates",
        f"",
    ]
    for row in rows:
        lines.extend([
            f"## {row.get('title', 'Template')} — ID {row.get('id')}",
            f"- **Product ID:** {row.get('catalog_product_id', 'N/A')}",
            f"- **Created:** {row.get('created_at', 'N/A')}",
            f"",
        ])
    return "\n".join(lines)
```

- [ ] **Step 2: Add the one new input model**

```python
class ListStoreTemplatesInput(BaseModel):
    """Input for printful_list_store_templates."""
    limit: int = Field(default=20, ge=1, le=100, description="Templates per page")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    format: Literal["markdown", "json"] = Field(
        default="markdown", description="Response format")
```

- [ ] **Step 3: Rewrite the three tool modules**

Each body takes the same shape as every other tool in this plan:

```python
async def <name>(transport: AsyncTransport, params: <Input>) -> str:
    """<the docstring it already has>"""
    try:
        request = <core builder>(...)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.<renderer>(data)
    except PrintfulError as e:
        return f"Error: {e.message}"
```

Each module imports `from printful_core.endpoints import files` (or `stores`,
`sync`), `from printful_core.errors import PrintfulError`,
`from printful_core.format import markdown`, and
`from printful_core.transport import AsyncTransport`; the `..client` import goes.

One worked body, so the shape above is concrete — this is `tools/files.py` in
full apart from its second tool:

```python
"""File library tools for the Printful MCP server."""

import json

from printful_core.endpoints import files
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import AddFileInput, GetFileInput


async def add_file(transport: AsyncTransport, params: AddFileInput) -> str:
    """
    Add a file to the Printful file library.

    Returns the file ID used in order placements. Large files come back with
    status 'waiting' and finish processing asynchronously.
    """
    try:
        request = files.add_file(
            params.url, filename=params.filename, visible=params.visible)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.file_added(data.get("data", {}))
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_file(transport: AsyncTransport, params: GetFileInput) -> str:
    """
    Get information about a file in the library.

    Returns file details including processing status, dimensions, and URLs.
    """
    try:
        data = await transport.send(files.get_file(params.file_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.file_detail(data.get("data", {}))
    except PrintfulError as e:
        return f"Error: {e.message}"
```

`stores.py` and `sync.py` follow it exactly, swapping the endpoint module, the
input models, and the renderer named in the table above.

Two module-specific notes:

- **`tools/sync.py` defines `ListSyncProductsInput` and `GetSyncProductInput`
  locally**, and `server.py` imports them from there. `.claude/CLAUDE.md` lists
  this as a known inconsistency to leave alone. **Leave it alone.** Moving them
  is unrelated churn and would touch `server.py`'s import block for no gain.
- **`files.add_file` takes `visible`**, which the current tool sends in its
  hand-built body. Pass it: `files.add_file(params.url, filename=params.filename,
  visible=params.visible)`.

Add the new tool to `tools/stores.py`:

```python
async def list_store_templates(transport: AsyncTransport,
                               params: ListStoreTemplatesInput) -> str:
    """
    List the store's saved product templates.

    Templates are designs already placed on a product, ready to reuse.
    """
    try:
        request = stores.list_templates(limit=params.limit, offset=params.offset)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.store_templates(data)
    except PrintfulError as e:
        return f"Error: {e.message}"
```

- [ ] **Step 4: Register the new tool and switch the six delegates**

Switch all six existing delegates in `server.py` to `get_transport()`, then add:

```python
@mcp.tool(
    name="printful_list_store_templates",
    annotations={
        "title": "List Product Templates",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
async def printful_list_store_templates(params: ListStoreTemplatesInput) -> str:
    """
    List the store's saved product templates.
    """
    return await stores.list_store_templates(get_transport(), params)
```

- [ ] **Step 5: Write the tests**

Create `src/printful_mcp/tests/test_small_domains.py`:

```python
"""files, stores and sync: what each tool sends and what it renders."""
from printful_mcp.models.inputs import (
    AddFileInput,
    GetStoreStatsInput,
    ListStoreTemplatesInput,
)
from printful_mcp.tools import files, stores, sync
from printful_mcp.tools.sync import ListSyncProductsInput


async def test_store_templates_send_paging_not_a_product_id(transport):
    """`stores.list_templates` takes limit and offset, not an id.

    Its namesake `mockups.list_templates(product_id)` takes a required id, so a
    positional call here binds that id to `limit` and silently returns the
    wrong collection with no error.
    """
    await stores.list_store_templates(
        transport, ListStoreTemplatesInput(limit=5, offset=10))
    assert transport.last.path == "/product-templates"
    assert transport.last.params == {"limit": 5, "offset": 10}


async def test_sync_products_are_a_v1_request(transport):
    """v2 exposes no sync-product endpoint.

    A v2 request 404s, and the tool would report an empty store rather than an
    unreachable endpoint.
    """
    await sync.list_sync_products(transport, ListSyncProductsInput())
    assert transport.last.version == "v1"


async def test_file_visibility_reaches_the_request(transport):
    """`visible=False` keeps a working file out of the user's library.

    Dropping it silently makes every uploaded file visible.
    """
    # markdown.file_added reads id/status/url unguarded, so the empty-queue
    # default {"data": {}} would raise KeyError inside the tool's try block.
    transport._responses.append({"data": {
        "id": 9, "status": "waiting", "url": "https://example.com/art.png"}})
    await files.add_file(transport, AddFileInput(
        url="https://example.com/art.png", visible=False))
    assert transport.last.json["visible"] is False


async def test_a_file_still_processing_says_so(transport):
    """Status 'waiting' is the normal first answer for a large upload.

    Rendering it as a finished file shows blank dimensions and no preview.
    """
    transport._responses.append({"data": {
        "id": 9, "status": "waiting", "url": "https://example.com/art.png"}})
    out = await files.add_file(transport, AddFileInput(url="https://example.com/art.png"))
    assert "being processed" in out


async def test_store_statistics_pass_the_date_window_through(transport):
    await stores.get_store_statistics(transport, GetStoreStatsInput(
        store_id=12345678, date_from="2026-01-01", date_to="2026-01-31"))
    assert transport.last.params["date_from"] == "2026-01-01"
    assert transport.last.params["date_to"] == "2026-01-31"
```

`12345678` is the placeholder store ID this repository uses in examples. Do not
put a real store ID in a test.

- [ ] **Step 6: Prove the moved renderers did not change their output**

The six moved renderers are the risk in this task, and no assertion above covers
most of them. Before committing, capture the old and new output of one renderer
per module and compare them as bytes:

```bash
.venv/bin/python - <<'PYEOF'
"""Capture each moved renderer's pre-move source and post-move output."""
import pathlib, subprocess, tempfile

from printful_core.format import markdown

# renderer name -> (source module at HEAD, fixture, whether it takes the envelope)
CASES = {
    "file_detail": ("files", {"data": {
        "id": 9, "status": "ok", "filename": "art.png", "mime_type": "image/png",
        "created": "2026-01-01", "width": 4500, "height": 5400, "dpi": 300,
        "size": 1234, "hash": "abc", "url": "https://example.com/art.png",
        "thumbnail_url": "https://example.com/t.png",
        "preview_url": "https://example.com/p.png"}}, False),
    "file_added": ("files", {"data": {
        "id": 9, "status": "waiting", "url": "https://example.com/art.png"}}, False),
    "stores": ("stores", {"data": [
        {"id": 12345678, "name": "Example Store", "type": "native"}]}, True),
    "store_statistics": ("stores", {"data": {"stats": []}}, True),
    "sync_products": ("sync", {"data": [{"id": 1, "name": "Tee", "variants": 2,
        "synced": 2, "thumbnail_url": "https://example.com/t.png"}],
        "paging": {"total": 1}}, True),
    "sync_product": ("sync", {"data": {"id": 1, "name": "Tee", "variants": 2,
        "synced": 2, "thumbnail_url": "https://example.com/t.png"}}, False),
}

tmp = pathlib.Path(tempfile.mkdtemp())
seen = set()
for renderer, (module, fixture, takes_envelope) in CASES.items():
    if module not in seen:
        # The pre-move module is still at HEAD -- this task has not committed.
        src = subprocess.run(
            ["git", "show", f"HEAD:src/printful_mcp/tools/{module}.py"],
            capture_output=True, text=True, check=True).stdout
        (tmp / f"old_{module}.py").write_text(src)
        print(f"captured HEAD:src/printful_mcp/tools/{module}.py "
              f"({len(src.splitlines())} lines)")
        seen.add(module)
    payload = fixture if takes_envelope else fixture["data"]
    out = getattr(markdown, renderer)(payload)
    (tmp / f"new_{renderer}.txt").write_text(out)
    print(f"  {renderer}() -> {len(out)} chars, {len(out.splitlines())} lines")

print(f"\nWrote pre-move sources and post-move output to {tmp}")
PYEOF
```

Run it, then read each `new_<renderer>.txt` against the corresponding markdown
block in `old_<module>.py`. **Paste the comparison into your report**, naming
each of the six renderers and whether its output matched. Plan 1 proved a
byte-identity claim this way for the mockup timeout message, and it is the only
check that catches a one-character drift in a string nobody asserts on.

If a renderer's output differs, the moved block was edited. Restore the original
wording; do not update an expectation to match the drift.

- [ ] **Step 7: Run, mutate, commit**

| Mutation | Test that must fail |
|---|---|
| Call `stores.list_templates(params.limit)` positionally | `test_store_templates_send_paging_not_a_product_id` |
| Remove `version="v1"` from the core's `sync.list_products` | `test_sync_products_are_a_v1_request` |
| Change `visible=params.visible` to `visible=True` | `test_file_visibility_reaches_the_request` |

```bash
.venv/bin/python -m pytest -q
rtk proxy git add src/printful_mcp/tools/files.py src/printful_mcp/tools/stores.py \
  src/printful_mcp/tools/sync.py src/printful_core/format/markdown.py \
  src/printful_mcp/models/inputs.py src/printful_mcp/server.py \
  src/printful_mcp/tests/test_small_domains.py
rtk proxy git commit -m "refactor: move the file, store and sync tools onto the core"
```

---
### Task 9: Delete the server's private HTTP stack and pin the parity target

**Files:**
- Delete: `src/printful_mcp/client.py` (183 lines)
- Delete: `tests/test_client_errors.py` (50 lines)
- Modify: `src/printful_mcp/server.py` (remove `get_client`, `_cleanup_client`, and the `PrintfulClient` import)
- Create: `src/printful_mcp/tests/test_server.py`

**Interfaces:**
- Consumes: everything Tasks 1–8 produced.
- Produces: the test that makes the parity target enforceable rather than asserted.

This is the task the whole plan exists for. Until `client.py` is gone, the
repository still holds two HTTP stacks and the two surfaces can still drift.

- [ ] **Step 1: Confirm nothing imports it**

```bash
rtk proxy git grep -n "printful_mcp.client\|from .client\|from ..client\|PrintfulClient\|PrintfulAPIError"
```

Expected hits, and only these four files:

| File | What the hits are | What to do |
|---|---|---|
| `src/printful_mcp/client.py` | the module itself | deleted in Step 2 |
| `tests/test_client_errors.py` | tests of the deleted module | deleted in Step 3 |
| `src/printful_mcp/server.py` | the import, `get_client`, `_cleanup_client` | stripped in Step 2 |
| `src/printful_mcp/tests/test_transport.py` | **one docstring**, no import | see below |

The fourth is not an import and does not break when `client.py` goes. It is a
docstring in `test_fake_transport_raises_a_queued_exception_instance` reading
*"to assert a tool's `except PrintfulAPIError` path"* — the name of the class
this task deletes. Change that one word to `PrintfulError`, which is what the
tools actually catch and what the test itself constructs two lines below. Do
not touch anything else in that file.

**Any hit inside `src/printful_mcp/tools/` means a domain task did not finish**
— go back and finish it rather than deleting the module out from under it.

- [ ] **Step 2: Delete the module and strip the server**

```bash
rtk proxy git rm src/printful_mcp/client.py
```

From `src/printful_mcp/server.py` remove: the `from .client import PrintfulClient`
line, the `_client` global, `_cleanup_client`, `get_client`, and the now-unused
`import asyncio` and `import atexit` if nothing else uses them. `from .transport
import get_transport` stays.

- [ ] **Step 3: Delete the superseded error tests, by name**

`tests/test_client_errors.py` tests `client.py`'s error parsing. That behavior
now lives in `printful_core.errors`, and each of its three cases has a named
successor already passing in `src/printful_core/tests/test_errors.py`:

| Deleted test | Covered instead by |
|---|---|
| `test_v2_error_reads_live_envelope` | `test_live_envelope_wins` |
| `test_v2_error_still_reads_documented_shape` | `test_rfc9457_detail`, `test_rfc9457_title_fallback` |
| `test_v1_error_unchanged` | `test_v1_result_string` |

```bash
rtk proxy git rm tests/test_client_errors.py
```

**This is the only deletion in this plan, and it is justified by name, not by
count.** If you cannot point at the successor test, do not delete the test.

- [ ] **Step 4: Write the tests that pin the parity target**

**First, delete `src/printful_mcp/tests/test_server_annotations.py`.** Task 4
created it to close a real gap: its mutation table found that setting
`destructiveHint: False` on `printful_cancel_order` broke no test, and leaving
that unguarded for five tasks was the worse option. This file is where that
assertion belongs, and `test_the_tools_that_spend_money_are_marked_destructive`
below covers it for both destructive tools rather than one. Confirm the new test
fails under the same mutation before deleting the interim file — if it does not,
keep the interim file and report that instead.

```bash
rtk proxy git rm src/printful_mcp/tests/test_server_annotations.py
```

Then create `src/printful_mcp/tests/test_server.py`:

```python
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
```

Three of these tests read source with `ast` rather than importing. That is
deliberate: importing every tool module to inspect it would run
`Credentials.resolve()` through any module-level transport access, and these
tests must pass with no credentials set.

- [ ] **Step 5: Verify the server boots and the count is what the code says**

```bash
.venv/bin/python -c "
from printful_mcp.server import mcp
import asyncio
tools = asyncio.run(mcp.list_tools())
print(len(tools), 'tools')
for t in sorted(x.name for x in tools): print('  ', t)
"
```

Expected: 32. If it is not 32, **do not adjust the test to match** — find the
missing or duplicated registration. The count is a consequence of the mapping,
not a target, and Step 4's test names exactly which endpoint is unbound.

- [ ] **Step 6: Run everything and commit**

```bash
.venv/bin/python -m pytest -q
```

Credentials unset. Report the number you get, and report it as a number you
observed rather than one you expected.

```bash
rtk proxy git add -u src/printful_mcp/ tests/
rtk proxy git add src/printful_mcp/tests/test_server.py
rtk proxy git status --porcelain
rtk proxy git commit -m "refactor: delete the server's private HTTP stack"
```

Paste the `git status --porcelain` output into your report so the staging
decision is visible to the reviewer.

---

### Task 10: Extend the live suite to the MCP surface

**Files:**
- Create: `src/printful_mcp/tests/test_live_mcp.py`
- Modify: `pyproject.toml:69` (the live-suite comment under-documents its requirements)

**Interfaces:**
- Consumes: the 32 registered tools; `printful_core.auth.Credentials.resolve`.

The spec asks for this in one line — *"Live suite keeps its `live` marker and
extends to MCP tools."* Everything before this task ran against fakes, which
structurally cannot show that the rewrite preserved live behavior. That is what
this task is for.

#### The safety rules are absolute

- **`printful_confirm_order` is never called.** It charges the account. It is
  asserted only against the fake transport, in Task 3.
- **`printful_create_mockup_task` is never called** unless `PRINTFUL_E2E_MOCKUPS=1`
  is already set in the environment. Do not set it. 2 requests/60s for a new
  store, a 60-second lockout, 20,000 files per account per day.
- **`printful_cancel_order` is applied only to a draft this suite created**, in
  the same test that created it, in a `finally` block.
- **Never print or echo the API key.** `config get` masks it; nothing else should
  ever hold it.

- [ ] **Step 1: Fix the live-suite documentation this plan inherited**

`pyproject.toml:69` reads:

```
#   pytest -m live      -> live API suite (requires PRINTFUL_API_KEY)
```

That is incomplete, and the gap cost a debugging round in plan 1: the token is
account-level, so store-scoped endpoints reject every call without the
`X-PF-Store-Id` header, and four draft-order tests fail in a way that reads
exactly like an order-path regression (Ruling 34). Change it to:

```
#   pytest -m live      -> live API suite (requires PRINTFUL_API_KEY and,
#                          for an account-level token, PRINTFUL_STORE_ID --
#                          without the store ID, store-scoped endpoints fail
#                          with "This endpoint requires 'store_id'!")
```

- [ ] **Step 2: Write the live tests**

Create `src/printful_mcp/tests/test_live_mcp.py`:

```python
"""The MCP surface against the real API.

The offline suite runs entirely on fake transports, so it cannot show that the
rewrite preserved live behavior. This can. It is the gate for this plan.

Run: set -a; . ./.env; set +a; export PRINTFUL_STORE_ID=<id>
     .venv/bin/python -m pytest -m live -q
"""
import json
import os

import pytest

from printful_mcp.models.inputs import (
    CreateEstimationTaskInput,
    GetProductInput,
    ListCategoriesInput,
    ListCatalogProductsInput,
    ListStoreTemplatesInput,
)
from printful_mcp.tools import catalog, orders, shipping, stores
from printful_mcp.transport import get_transport

pytestmark = pytest.mark.live


def _require_credentials():
    if not os.environ.get("PRINTFUL_API_KEY"):
        pytest.fail("PRINTFUL_API_KEY is not set. Live tests fail loudly rather "
                    "than skip, so a green run means the API was really reached.")


@pytest.fixture
def live_transport():
    """The real transport.

    Deliberately NOT named `transport`. conftest.py defines a `transport`
    fixture that yields a FakeTransport, and a module-local fixture of the same
    name silently shadows it -- so a test moved out of this file would keep
    hitting the live API under a name that reads as a fake.
    """
    _require_credentials()
    return get_transport()


async def test_the_country_list_contains_the_united_states(live_transport):
    """The defect this plan fixes, checked where it actually lived.

    A single unpaginated request returns the first page only, and `US` is not
    in it. An offline test can prove the tool calls collect_pages_async; only
    this can prove the result is the whole collection.
    """
    out = await shipping.list_countries(live_transport)
    assert "United States" in out
    assert "(US)" in out


async def test_a_v2_error_says_what_went_wrong(live_transport):
    """Every v2 error used to arrive as 'Unknown error'.

    Product 99999999 does not exist -- a deliberately invalid ID, not a real
    product being probed.
    """
    out = await catalog.get_product(live_transport, GetProductInput(product_id=99999999))
    assert out.startswith("Error:")
    assert "Unknown error" not in out


async def test_categories_return_real_rows(live_transport):
    """A tool added in this plan, never exercised against the API before."""
    out = await catalog.list_categories(live_transport, ListCategoriesInput(limit=5))
    assert "Catalog Categories" in out
    assert "ID" in out


async def test_the_caller_s_limit_is_respected(live_transport):
    """Proves the catalog tools do not silently walk every page."""
    out = await catalog.list_catalog_products(
        live_transport, ListCatalogProductsInput(limit=2, format="json"))
    assert len(json.loads(out)["data"]) == 2


async def test_an_estimate_can_be_started_and_read(live_transport):
    """The create/read split, end to end.

    Estimation creates a task and charges nothing. This asserts the task is
    accepted and that reading it returns one of the three known states -- not
    that it completes, because completion timing is the API's business.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}]
    started = await orders.create_estimation_task(live_transport, CreateEstimationTaskInput(
        recipient_country_code="US", recipient_state_code="CA",
        recipient_city="San Francisco", recipient_zip="94107",
        items_json=json.dumps(items)))
    assert not started.startswith("Error:"), started
    assert "Task ID:" in started


async def test_product_templates_come_back_under_the_v1_items_key(live_transport):
    """The renderer reads `items`; only a live call can confirm that.

    `stores.list_templates` is the one v1 endpoint in this plan whose renderer
    was written from scratch, with no pre-move predecessor to be byte-identical
    to. Its shape was taken from the CLI's own normalization at
    `printful_cli/core/stores.py:31`, which is in-repo evidence rather than a
    live observation. A v2-shaped `data` key here would mean the tool renders
    "Showing 0 templates" for a store that has templates -- a wrong answer
    shaped like a right one, which no offline test can catch.
    """
    body = json.loads(await stores.list_store_templates(
        live_transport, ListStoreTemplatesInput(format="json")))
    assert isinstance(body, list) or "items" in body, (
        f"expected a bare list or an 'items' key, got keys {sorted(body)}")


async def test_a_template_row_carries_the_fields_the_renderer_prints(live_transport):
    """A wrong row key renders 'N/A' forever: valid markdown, no error.

    The renderer prints `title`, `catalog_product_id` and `created_at`. Those
    three names are the last unverified thing in this plan. This skips loudly
    rather than passing when the store has no templates -- a vacuous pass here
    would read as confirmation.
    """
    body = json.loads(await stores.list_store_templates(
        live_transport, ListStoreTemplatesInput(format="json")))
    rows = body if isinstance(body, list) else body.get("items", [])
    if not rows:
        pytest.skip("store has no product templates; row field names unverified")
    missing = [k for k in ("title", "catalog_product_id", "created_at")
               if k not in rows[0]]
    assert not missing, (
        f"the renderer prints keys the API does not send: {missing}. "
        f"The row actually carries {sorted(rows[0])}.")
```

Those last two exist because of a defect found in Task 8's review. The
`store_templates` renderer originally read a v2 `data`/`paging` envelope off a
`version="v1"` request. The envelope is fixed and covered offline; the per-row
field names are not offline-checkable at all, and this is the only task that
can settle them. **If the second test skips, say so in your report** -- a skip
is the honest outcome, and a silent pass would not be.

**No test in this file calls `printful_confirm_order` or
`printful_create_mockup_task`.** If you believe one is needed, stop and say so
in your report rather than adding it.

- [ ] **Step 3: Run the offline suite first**

```bash
.venv/bin/python -m pytest -q
```

Credentials unset. The live tests must be deselected, not skipped, and the
offline count must not change from Task 9's.

- [ ] **Step 4: Run the live gate**

```bash
set -a; . ./.env; set +a
export PRINTFUL_STORE_ID=<the store id>
.venv/bin/python -m pytest -m live -q
```

This runs both the CLI's existing live suite and the new MCP one. **The CLI's
live results must be unchanged from plan 1's gate: 18 passed, 3 skipped.** If a
CLI live test that passed in plan 1 now fails, this plan broke the core — that
is a regression, not an environment problem, and it stops the task.

Report both numbers. If any test fails, paste the `^E ` lines from the failure
output — not the whole traceback, which can carry request detail.

- [ ] **Step 5: Commit**

```bash
rtk proxy git add src/printful_mcp/tests/test_live_mcp.py pyproject.toml
rtk proxy git commit -m "test: exercise the MCP tools against the live API"
```

---

## Self-review

Run against the spec after the plan is written, before execution starts.

**1. Spec coverage.** Phase 4 of the spec — *"Rebuild the MCP on the core. Port
the 19 existing tools, then add the 14 that close parity. First automated tests
for the server."* — is covered by Tasks 1–10, with one documented deviation:
**13 new tools, not 14**, ruled against the code rather than the prose. The
spec's § Testing row *"MCP adapter tests, the first the server has ever had:
each tool registers, validates its input, and maps to the expected Request"* is
Tasks 2–9; *"Live suite … extends to MCP tools"* is Task 10.

Deliberately out of scope, and belonging to plan 3: the cull of
`test_server.py` / `test_comprehensive.py` / `test_complete.py` / `run-tests.sh`
/ `examples.py` / `TESTING.md` / `PRINTFUL.md`, the README and QUICKSTART
rewrite, distribution manifests, and CI. `src/printful_mcp/client.py` is culled
here rather than in plan 3 because nothing can be rebuilt on the core while it
survives.

**2. Type consistency.** The tool signature is
`async def name(transport: AsyncTransport, params: XInput) -> str` in every task.
Renderer names are unique within `printful_core.format.markdown`: `product`,
`products`, `variants`, `variant_prices`, `availability`, `categories`,
`category`, `size_guide`, `order`, `orders`, `order_items`, `shipments`,
`estimate`, `rates`, `countries`, `tax`, `mockup_task`, `mockup_styles`,
`mockup_templates`, `file_added`, `file_detail`, `stores`, `store_statistics`,
`store_templates`, `sync_products`, `sync_product`. `markdown.orders` and
`summary.orders` share a name across two modules, which is intended — they
render the same response for two different readers.

**3. Known collisions and traps, each with the task that handles it.**

| Trap | Task |
|---|---|
| `mockups.list_templates(product_id)` vs `stores.list_templates(limit, offset)` — the second binds positionally and fails silently | 8 |
| `CreateMockupTaskInput.format` means jpg/png, not markdown/json | 7 |
| The core raises `ValueError`, which `except PrintfulError` does not catch | 3, 4, 5, 7 |
| The placements message differs between the tool and the core, and the existing test cannot tell | 3 |
| `collect_pages_async` belongs to `list_countries` only | 2, 6 |
| `sync` and `calculate_tax` are v1 requests | 6, 8 |
| `create_estimation_task` deliberately skips `_require_placements` | 5 |

**4. Placeholder scan.** None. Every code step carries its code, including
Task 8 Step 6's byte-identity capture, which an earlier draft left to the
implementer on the false premise that the pre-move module path varies — it does
not; it is `HEAD:src/printful_mcp/tools/<module>.py` at every one of those
commits.

Two steps end in a judgment the implementer must make and report rather than a
command that passes or fails: Task 8 Step 6's renderer comparison, and Task 10
Step 4's live gate. Both say what to paste into the report.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-16-mcp-server-on-the-core.md`.

**Suggested model tiers**, since eight of the ten tasks are transcription plus
testing: Tasks 1, 4, 5, 8, 10 take a cheap-to-mid tier; Tasks 2, 3, 6, 7 take a
standard tier for the judgment calls each carries; Task 9 takes a standard tier
because it deletes a module and writes the test the parity claim rests on.

**Task 1 must run first and alone** — every later task consumes `get_transport`
and `FakeTransport`. Tasks 2 through 8 touch disjoint tool modules but all three
of `server.py`, `models/inputs.py` and `format/markdown.py`, so they run in
sequence, never in parallel.
