# Printful Core Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land three upstream-able fixes as isolated tagged commits, then extract a shared `printful_core` that performs no I/O and move the CLI onto it.

**Architecture:** Every API operation becomes a pure function returning a frozen `Request(method, path, version, params, json)`. The core never touches the network; a `SyncTransport` and an `AsyncTransport` execute requests. This puts endpoint paths, payload shapes, and error parsing — the source of all five known defects — in one place that tests can reach without a network call.

**Tech Stack:** Python 3.10+, httpx (sync + async), Click, pytest. No `requests` after Task 8.

**Spec:** `docs/superpowers/specs/2026-09-16-printful-merger-design.md`

## Global Constraints

- **`mcp` must stay `<2`.** Version 2.x renamed `FastMCP` to `MCPServer`; the server fails at import otherwise.
- **Tasks 1–3 must not reference `printful_core`.** They are cherry-picked to a branch cut from `upstream/main`, which has no such package.
- **`pytest` must pass offline with no credentials.** Live tests carry `@pytest.mark.live` and are deselected by `addopts = "-m 'not live'"`.
- **`orders confirm` charges real money.** Never call it against the live API in a test. It is asserted only against a fake transport.
- **API base URLs:** v2 is `https://api.printful.com/v2`, v1 is `https://api.printful.com`.
- **v1 success unwraps** `{"code", "result"}` to `result`. v2 returns its body unchanged.
- **Error envelopes:** the live API returns `{"data": "<msg>", "error": {"reason", "message"}}` for both v1 and v2. RFC 9457 (`detail`/`title`) is documented but not returned; read both.
- **Store context:** `X-PF-Store-Id` is sent only when a store ID is configured. Account-level tokens require it; store-level tokens must not send it.
- **Attribution:** no `Co-Authored-By` trailers naming an agent in any commit message.

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `src/printful_core/__init__.py` | Package marker, version |
| `src/printful_core/request.py` | The frozen `Request` dataclass |
| `src/printful_core/errors.py` | Exception types and `normalize_error` |
| `src/printful_core/auth.py` | Credential resolution, header construction |
| `src/printful_core/transport.py` | `SyncTransport`, `AsyncTransport` |
| `src/printful_core/pagination.py` | `collect_pages` |
| `src/printful_core/endpoints/*.py` | Pure request builders, one module per domain |
| `src/printful_core/format/summary.py` | Response flatteners for tabular display |
| `src/printful_core/tests/*.py` | Core unit tests |

**Modified:** `pyproject.toml`, `src/printful_mcp/client.py`, `src/printful_mcp/models/inputs.py`, `src/printful_mcp/tools/orders.py`

**Moved:** `src/cli_anything/printful/` → `src/printful_cli/`

**Deleted:** `src/printful_cli/utils/printful_backend.py`, `src/printful_cli/utils/repl_skin.py`

---

## Task 1: Isolate the `mcp<2` pin as an upstream commit

The working tree currently mixes the pin with fork-only packaging in one file. Committing as-is strands the pin and makes it uncherry-pickable.

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing
- Produces: commit 1 of the upstream series

- [ ] **Step 1: Inspect what is currently mixed together**

```bash
git diff pyproject.toml
```

Expected: one hunk adding `mcp<2`, plus hunks adding `click`/`requests`/`prompt_toolkit`, `[tool.pytest.ini_options]`, `namespaces = true`, `[tool.setuptools.package-data]`, and a second `[project.scripts]` entry.

- [ ] **Step 2: Verify the break is real before fixing it**

```bash
.venv/bin/python -m pip install 'mcp>=2' -q
.venv/bin/python -c "from printful_mcp.server import mcp"
```

Expected: `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`

- [ ] **Step 3: Restore the pin and confirm recovery**

```bash
.venv/bin/python -m pip install 'mcp<2' -q
.venv/bin/python -c "
from printful_mcp.server import mcp
import asyncio
print('tools:', len(asyncio.run(mcp.list_tools())))
"
```

Expected: `tools: 19`

- [ ] **Step 4: Stage only the pin hunk**

```bash
git add -p pyproject.toml
```

Accept only the hunk containing `"mcp>=0.9.0,<2"`. Reject every other hunk. If the hunks are adjacent and cannot be split, press `e` and edit manually so only the dependency line changes.

- [ ] **Step 5: Verify nothing else is staged**

```bash
git diff --cached
```

Expected: exactly one changed line in `dependencies`, plus its explanatory comment. If anything else appears, run `git restore --staged pyproject.toml` and redo Step 4.

- [ ] **Step 6: Commit**

```bash
git commit -m "fix: pin mcp<2 so the server can import

mcp 2.x renamed FastMCP to MCPServer. With an unpinned floor of 0.9.0, a
fresh install resolves to 2.x and server.py raises ModuleNotFoundError at
import, so the server never starts.

Reproduce on a clean checkout:

    pip install -e .
    python -c 'from printful_mcp.server import mcp'
    ModuleNotFoundError: No module named 'mcp.server.fastmcp'

With the pin, the server imports and registers all 19 tools. Migrating to
the 2.x MCPServer API is worth doing separately; this restores service now."
```

---

## Task 2: Fix v2 error parsing as an upstream commit

**Files:**
- Modify: `src/printful_mcp/client.py:138-146`
- Create: `tests/test_client_errors.py`

**Interfaces:**
- Consumes: nothing
- Produces: commit 2 of the upstream series

- [ ] **Step 1: Write the failing test**

Create `tests/test_client_errors.py`:

```python
"""Error-parsing tests for the Printful client. No network."""
import pytest

from printful_mcp.client import PrintfulClient, PrintfulAPIError


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRINTFUL_API_KEY", "test-token")
    return PrintfulClient()


@pytest.mark.asyncio
async def test_v2_error_reads_live_envelope(client):
    """The live v2 API returns error.message, not RFC 9457 detail/title."""
    response = FakeResponse(404, {
        "data": "Product 99999999 does not exist or is inactive.",
        "error": {"reason": "NotFound",
                  "message": "Product 99999999 does not exist or is inactive."},
    })
    with pytest.raises(PrintfulAPIError) as exc:
        await client._handle_error(response, "v2")
    assert "does not exist or is inactive" in exc.value.message
    assert exc.value.message != "Unknown error"


@pytest.mark.asyncio
async def test_v2_error_still_reads_documented_shape(client):
    """RFC 9457 is documented, so keep supporting it."""
    response = FakeResponse(400, {"detail": "Bad variant", "title": "Invalid"})
    with pytest.raises(PrintfulAPIError) as exc:
        await client._handle_error(response, "v2")
    assert exc.value.message == "Bad variant"


@pytest.mark.asyncio
async def test_v1_error_unchanged(client):
    response = FakeResponse(404, {"code": 404, "error": {"message": "Not Found"}})
    with pytest.raises(PrintfulAPIError) as exc:
        await client._handle_error(response, "v1")
    assert exc.value.message == "Not Found"
```

- [ ] **Step 2: Add the async test dependency and run the test to see it fail**

```bash
.venv/bin/python -m pip install pytest-asyncio -q
.venv/bin/python -m pytest tests/test_client_errors.py -v -p no:cacheprovider \
    -o asyncio_mode=auto -o addopts=""
```

Expected: `test_v2_error_reads_live_envelope` FAILS with `assert 'does not exist or is inactive' in 'Unknown error'`. The other two PASS.

- [ ] **Step 3: Fix the parser**

In `src/printful_mcp/client.py`, replace the `if version == "v2":` branch of `_handle_error`:

```python
        # v2 is documented as RFC 9457, but the live API returns the v1-style
        # envelope ({"data": "...", "error": {"reason", "message"}}) for 4xx
        # and 404 alike, so read that first and fall back to the documented
        # shape. Verified against live 400 and 404 responses.
        if version == "v2":
            error_msg = (
                error_data.get("error", {}).get("message")
                or error_data.get("detail")
                or error_data.get("title")
                or "Unknown error"
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_client_errors.py -v -p no:cacheprovider \
    -o asyncio_mode=auto -o addopts=""
```

Expected: 3 passed.

- [ ] **Step 5: Add pytest-asyncio to the dev extra**

In `pyproject.toml`, under `[project.optional-dependencies]`, the `dev` list already contains `pytest-asyncio>=0.21.0`. Confirm with:

```bash
grep -n 'pytest-asyncio' pyproject.toml
```

Expected: a match. If absent, add `"pytest-asyncio>=0.21.0",` to the `dev` list and stage that single line.

- [ ] **Step 6: Commit**

```bash
git add src/printful_mcp/client.py tests/test_client_errors.py
git commit -m "fix: read the v2 error envelope the API actually returns

The v2 docs describe RFC 9457 problem details, so _handle_error read
detail/title. The live API returns the v1-style envelope instead, for both
400 and 404:

    {\"data\": \"Product 99999999 does not exist or is inactive.\",
     \"error\": {\"reason\": \"NotFound\", \"message\": \"...\"}}

Neither detail nor title is present, so every v2 error reached the caller as
\"Unknown error\" and hid its own cause. Read the returned shape first and
keep the documented one as a fallback.

Verified against live 404 (catalog-products/99999999) and 400
(shipping-rates with no store context) responses."
```

---

## Task 3: Accept order items when creating an order

`create_order` sends only a recipient. No tool adds items afterwards, so an order created through the MCP can never be filled. Printful also rejects a catalog item with no `placements` — there is nothing to print.

**Files:**
- Modify: `src/printful_mcp/models/inputs.py` (`CreateOrderInput`)
- Modify: `src/printful_mcp/tools/orders.py:73-108` (`create_order`)
- Create: `tests/test_create_order.py`

**Interfaces:**
- Consumes: nothing
- Produces: commit 3 of the upstream series; `CreateOrderInput.items_json: str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_create_order.py`:

```python
"""Order-creation payload tests. No network."""
import json
import pytest

from printful_mcp.models.inputs import CreateOrderInput
from printful_mcp.tools.orders import create_order


class RecordingClient:
    """Captures the payload instead of sending it."""

    def __init__(self):
        self.posted = None

    async def post(self, endpoint, json_data, **kwargs):
        self.posted = {"endpoint": endpoint, "json": json_data}
        return {"data": {"id": 1, "status": "draft", "recipient": {}, "costs": {}}}


def _recipient_kwargs():
    return dict(
        recipient_name="Jane Doe",
        recipient_address1="1 Main St",
        recipient_city="Charlotte",
        recipient_state_code="NC",
        recipient_country_code="US",
        recipient_zip="28273",
    )


@pytest.mark.asyncio
async def test_order_items_reach_the_request():
    client = RecordingClient()
    params = CreateOrderInput(
        items_json=json.dumps([
            {"source": "catalog", "catalog_variant_id": 4012, "quantity": 2,
             "placements": [{"placement": "front", "technique": "dtg",
                             "layers": [{"type": "file",
                                         "url": "https://example.com/a.png"}]}]}
        ]),
        **_recipient_kwargs(),
    )
    await create_order(client, params)
    items = client.posted["json"]["order_items"]
    assert len(items) == 1
    assert items[0]["catalog_variant_id"] == 4012
    assert items[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_catalog_item_without_placements_is_rejected_before_sending():
    """Printful returns 'Property placements is required'. Fail early instead."""
    client = RecordingClient()
    params = CreateOrderInput(
        items_json=json.dumps([
            {"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}
        ]),
        **_recipient_kwargs(),
    )
    result = await create_order(client, params)
    assert "placements" in result
    assert client.posted is None


@pytest.mark.asyncio
async def test_invalid_json_is_reported_clearly():
    client = RecordingClient()
    params = CreateOrderInput(items_json="not json", **_recipient_kwargs())
    result = await create_order(client, params)
    assert "valid JSON" in result
    assert client.posted is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_create_order.py -v -p no:cacheprovider \
    -o asyncio_mode=auto -o addopts=""
```

Expected: all three FAIL — `CreateOrderInput` has no `items_json` field, so construction raises `ValidationError`.

- [ ] **Step 3: Add the field to the input model**

In `src/printful_mcp/models/inputs.py`, inside `CreateOrderInput`, add after `external_id`:

```python
    items_json: str = Field(
        ...,
        description=(
            "JSON array of order items. Each catalog item needs source, "
            "catalog_variant_id, quantity, and placements (Printful rejects an "
            "item with no artwork). Example: "
            '[{"source":"catalog","catalog_variant_id":4012,"quantity":1,'
            '"placements":[{"placement":"front","technique":"dtg",'
            '"layers":[{"type":"file","url":"https://example.com/art.png"}]}]}]'
        ),
    )
```

- [ ] **Step 4: Build the items into the request**

In `src/printful_mcp/tools/orders.py`, inside `create_order`, immediately after the `order_data` dictionary is built and before `client.post` is called:

```python
        try:
            items = json.loads(params.items_json)
        except json.JSONDecodeError as e:
            return f"Error: items_json must be valid JSON array ({e})."

        if not isinstance(items, list) or not items:
            return "Error: items_json must be a non-empty JSON array of order items."

        for index, item in enumerate(items):
            if item.get("source", "catalog") == "catalog" and not item.get("placements"):
                return (
                    f"Error: order_items[{index}] has no placements. Printful "
                    "rejects a catalog item with no artwork. Add placements, e.g. "
                    '[{"placement":"front","technique":"dtg","layers":'
                    '[{"type":"file","url":"https://example.com/art.png"}]}]'
                )

        order_data["order_items"] = items
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_create_order.py -v -p no:cacheprovider \
    -o asyncio_mode=auto -o addopts=""
```

Expected: 3 passed.

- [ ] **Step 6: Update the tool docstring**

In `src/printful_mcp/server.py`, the `printful_create_order` docstring currently says items are added separately. Replace that sentence:

```
    Creates an order in draft status with its items. Drafts are not charged
    until confirmed. Each catalog item requires placements (artwork).
```

- [ ] **Step 7: Commit and tag**

```bash
git add src/printful_mcp/models/inputs.py src/printful_mcp/tools/orders.py \
        src/printful_mcp/server.py tests/test_create_order.py
git commit -m "feat: accept order items when creating an order

create_order sent only a recipient, and no tool adds items to an existing
order, so an order created through the MCP could never be filled. The
docstring pointed at an add_order_item tool that does not exist.

Add items_json to CreateOrderInput and pass the parsed array as order_items.
Reject a catalog item with no placements before sending: Printful returns
'Property \`placements\` is required' because it has nothing to print, and
failing early gives a clearer message than the API does.

Verified live: POST /v2/orders with recipient and no order_items returns 200
and an empty draft that cannot be fulfilled; with order_items carrying
placements it returns a draft containing the items."
git tag upstream-base
```

---

## Task 4: Create `printful_core` with the `Request` type

**Files:**
- Create: `src/printful_core/__init__.py`, `src/printful_core/request.py`
- Create: `src/printful_core/tests/__init__.py`, `src/printful_core/tests/test_request.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing
- Produces: `Request(method, path, version="v2", params=None, json=None)` — frozen dataclass with `.with_params(**kw)`

- [ ] **Step 1: Write the failing test**

Create `src/printful_core/tests/test_request.py`:

```python
import dataclasses
import pytest

from printful_core.request import Request


def test_request_defaults_to_v2():
    req = Request("GET", "/catalog-products")
    assert req.version == "v2"
    assert req.params == {}
    assert req.json is None


def test_request_is_frozen():
    req = Request("GET", "/countries")
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.path = "/other"


def test_none_params_are_dropped():
    req = Request("GET", "/catalog-products", params={"limit": 5, "colors": None})
    assert req.params == {"limit": 5}


def test_with_params_returns_a_new_request():
    original = Request("GET", "/countries", params={"limit": 20})
    updated = original.with_params(offset=40)
    assert updated.params == {"limit": 20, "offset": 40}
    assert original.params == {"limit": 20}
    assert updated.path == original.path


def test_v1_version_is_preserved():
    assert Request("GET", "/store/products", version="v1").version == "v1"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_request.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'printful_core'`

- [ ] **Step 3: Write the implementation**

Create `src/printful_core/__init__.py`:

```python
"""Shared Printful API core: request specs, transport, errors, formatting."""

__version__ = "1.0.0"
```

Create `src/printful_core/tests/__init__.py` (empty file).

Create `src/printful_core/request.py`:

```python
"""The request description shared by every Printful surface.

A Request says what to send without sending it. Building one performs no I/O,
so endpoint paths and payload shapes can be asserted without a network call —
and the same description serves a synchronous CLI and an asynchronous server.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Request:
    """An un-sent Printful API call."""

    method: str
    path: str
    version: str = "v2"
    params: Dict[str, Any] = field(default_factory=dict)
    json: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        # Callers pass optional filters straight through; dropping None here
        # keeps every endpoint builder free of the same three-line dance.
        cleaned = {k: v for k, v in (self.params or {}).items() if v is not None}
        object.__setattr__(self, "params", cleaned)

    def with_params(self, **extra: Any) -> "Request":
        """Return a copy with additional query parameters."""
        merged = {**self.params, **extra}
        return replace(self, params=merged)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_request.py -v -o addopts=""
```

Expected: 5 passed.

- [ ] **Step 5: Add the package to the build and the test path**

In `pyproject.toml`, change the pytest `testpaths` line to cover both suites:

```toml
testpaths = ["src/printful_core/tests", "src/cli_anything/printful/tests", "tests"]
```

- [ ] **Step 6: Reinstall and confirm discovery**

```bash
.venv/bin/python -m pip install -e . -q
.venv/bin/python -c "import printful_core; print(printful_core.__version__)"
```

Expected: `1.0.0`

- [ ] **Step 7: Commit**

```bash
git add src/printful_core pyproject.toml
git commit -m "feat: add printful_core.Request, an un-sent API call

A Request describes what to send without sending it, so endpoint paths and
payload shapes become assertable without a network call, and one description
serves both the synchronous CLI and the asynchronous MCP server."
```

---

## Task 5: Error normalization in the core

**Files:**
- Create: `src/printful_core/errors.py`, `src/printful_core/tests/test_errors.py`

**Interfaces:**
- Consumes: nothing
- Produces: `PrintfulError(message, status_code, detail)`, `PrintfulAuthError`, `PrintfulRateLimitError(retry_after)`, `extract_message(body) -> str | None`, `raise_for_status(status, body, url)`

- [ ] **Step 1: Write the failing test**

Create `src/printful_core/tests/test_errors.py`:

```python
import pytest

from printful_core.errors import (
    PrintfulAuthError,
    PrintfulError,
    PrintfulRateLimitError,
    extract_message,
    raise_for_status,
)


class TestExtractMessage:
    def test_live_envelope_wins(self):
        body = {"data": "msg", "error": {"reason": "NotFound", "message": "real"}}
        assert extract_message(body) == "real"

    def test_rfc9457_detail(self):
        assert extract_message({"detail": "Bad variant"}) == "Bad variant"

    def test_rfc9457_title_fallback(self):
        assert extract_message({"title": "Invalid"}) == "Invalid"

    def test_data_string_only(self):
        assert extract_message({"data": "plain"}) == "plain"

    def test_v1_result_string(self):
        assert extract_message({"code": 404, "result": "Not Found"}) == "Not Found"

    def test_plain_string_body(self):
        assert extract_message("boom") == "boom"

    def test_unrecognized_body(self):
        assert extract_message({"weird": {"nested": 1}}) is None


class TestRaiseForStatus:
    def test_401_mentions_expiry(self):
        with pytest.raises(PrintfulAuthError, match="expire"):
            raise_for_status(401, {}, "https://api.printful.com/v2/orders")

    def test_403_mentions_scope(self):
        with pytest.raises(PrintfulAuthError, match="scope"):
            raise_for_status(403, {}, "https://api.printful.com/v2/orders")

    @pytest.mark.parametrize("status", [429, 419])
    def test_rate_limit_carries_retry_after(self, status):
        with pytest.raises(PrintfulRateLimitError) as exc:
            raise_for_status(status, {}, "url", headers={"Retry-After": "30"})
        assert exc.value.retry_after == "30"

    def test_rate_limit_message_names_mockup_limits(self):
        with pytest.raises(PrintfulRateLimitError, match="2/60s"):
            raise_for_status(429, {}, "url", headers={})

    def test_error_message_and_status_preserved(self):
        body = {"data": "m", "error": {"reason": "BadRequest", "message": "m"}}
        with pytest.raises(PrintfulError) as exc:
            raise_for_status(400, body, "url")
        assert exc.value.message == "m"
        assert exc.value.status_code == 400
        assert exc.value.detail == body

    def test_unrecognized_body_names_the_status(self):
        with pytest.raises(PrintfulError, match="status 500"):
            raise_for_status(500, {"weird": 1}, "https://api.printful.com/v2/x")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_errors.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'printful_core.errors'`

- [ ] **Step 3: Write the implementation**

Create `src/printful_core/errors.py`:

```python
"""Printful error types and envelope normalization.

The v2 documentation describes RFC 9457 problem details, but the live API
returns the v1-style envelope for both 4xx and 404:

    {"data": "<message>", "error": {"reason": "...", "message": "..."}}

Reading only detail/title reduces every real error to "Unknown error" and hides
its cause, so every known shape is tried here regardless of API version.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

TOKEN_HELP = (
    "Get a token at https://www.printful.com/dashboard/api\n"
    "Then either:\n"
    "  export PRINTFUL_API_KEY=your-token\n"
    "  printful config set api_key your-token"
)

RATE_LIMIT_HELP = (
    "The general limit is 120 requests/60s. Mockup creation is far stricter: "
    "10/60s for established stores and 2/60s for new stores, with a 60s lockout."
)


class PrintfulError(Exception):
    """A Printful API error, normalized across every envelope shape."""

    def __init__(self, message: str, status_code: Optional[int] = None,
                 detail: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {"error": self.message, "status_code": self.status_code,
                "detail": self.detail}


class PrintfulAuthError(PrintfulError):
    """Missing, invalid, expired, or under-scoped credentials."""


class PrintfulRateLimitError(PrintfulError):
    """Rate limited. Carries Retry-After when the API supplied it."""

    def __init__(self, message: str, retry_after: Optional[str] = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


def extract_message(body: Any) -> Optional[str]:
    """Pull a human-readable message out of any known Printful error shape."""
    if isinstance(body, str):
        return body or None
    if not isinstance(body, dict):
        return None

    error = body.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    if isinstance(error, str) and error:
        return error

    for key in ("detail", "title", "data", "result", "message"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def raise_for_status(status: int, body: Any, url: str,
                     headers: Optional[Mapping[str, str]] = None) -> None:
    """Raise the appropriate PrintfulError for a non-2xx response."""
    headers = headers or {}

    if status == 401:
        raise PrintfulAuthError(
            "Unauthorized. The token may be invalid, expired, or missing a "
            "required scope.\nPrintful private tokens expire and cannot be "
            "refreshed — they must be regenerated.\n" + TOKEN_HELP,
            status_code=401,
        )

    if status == 403:
        raise PrintfulAuthError(
            "Forbidden. The token is valid but lacks the scope for this "
            "endpoint. Check its scopes in the Printful dashboard.",
            status_code=403,
        )

    if status in (429, 419):
        retry_after = headers.get("Retry-After", "60")
        raise PrintfulRateLimitError(
            f"Rate limit exceeded. Retry after {retry_after} seconds. "
            + RATE_LIMIT_HELP,
            retry_after=retry_after,
            status_code=status,
        )

    message = extract_message(body)
    raise PrintfulError(
        message or f"Request to {url} failed with status {status}",
        status_code=status,
        detail=body if isinstance(body, dict) else {"body": body},
    )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_errors.py -v -o addopts=""
```

Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add src/printful_core/errors.py src/printful_core/tests/test_errors.py
git commit -m "feat: normalize every Printful error envelope in one place

The live v2 API returns the v1-style {data, error.message} envelope rather
than the RFC 9457 detail/title the docs describe. Reading one shape hid the
cause of every v2 error, so read all of them."
```

---

## Task 6: Credential and header resolution

**Files:**
- Create: `src/printful_core/auth.py`, `src/printful_core/tests/test_auth.py`

**Interfaces:**
- Consumes: `printful_core.errors.PrintfulAuthError`
- Produces: `Credentials(api_key, store_id)`, `Credentials.resolve(api_key=None, store_id=None)`, `Credentials.headers() -> dict`, `CONFIG_FILE`, `load_config()`, `save_config(dict)`

- [ ] **Step 1: Write the failing test**

Create `src/printful_core/tests/test_auth.py`:

```python
import pytest

from printful_core import auth
from printful_core.errors import PrintfulAuthError


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.delenv("PRINTFUL_API_KEY", raising=False)
    monkeypatch.delenv("PRINTFUL_STORE_ID", raising=False)
    monkeypatch.setattr(auth, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(auth, "CONFIG_FILE", tmp_path / "config.json")


def test_explicit_key_beats_environment(monkeypatch):
    monkeypatch.setenv("PRINTFUL_API_KEY", "from-env")
    assert auth.Credentials.resolve(api_key="explicit").api_key == "explicit"


def test_environment_beats_config(monkeypatch):
    auth.save_config({"api_key": "from-config"})
    monkeypatch.setenv("PRINTFUL_API_KEY", "from-env")
    assert auth.Credentials.resolve().api_key == "from-env"


def test_config_used_when_nothing_else_set():
    auth.save_config({"api_key": "from-config"})
    assert auth.Credentials.resolve().api_key == "from-config"


def test_missing_key_raises_with_instructions():
    with pytest.raises(PrintfulAuthError, match="printful.com/dashboard/api"):
        auth.Credentials.resolve()


def test_headers_always_carry_bearer_token():
    creds = auth.Credentials(api_key="tok", store_id=None)
    assert creds.headers()["Authorization"] == "Bearer tok"
    assert creds.headers()["Content-Type"] == "application/json"


def test_store_header_present_only_when_set():
    assert "X-PF-Store-Id" not in auth.Credentials("tok", None).headers()
    assert auth.Credentials("tok", "42").headers()["X-PF-Store-Id"] == "42"


def test_store_id_coerced_to_string():
    assert auth.Credentials.resolve(api_key="t", store_id=42).store_id == "42"


def test_config_round_trip():
    auth.save_config({"api_key": "k", "store_id": "9"})
    assert auth.load_config() == {"api_key": "k", "store_id": "9"}


def test_corrupt_config_reads_as_empty():
    auth.CONFIG_FILE.write_text("{not json")
    assert auth.load_config() == {}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_auth.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'printful_core.auth'`

- [ ] **Step 3: Write the implementation**

Create `src/printful_core/auth.py`:

```python
"""Credential resolution and request headers.

X-PF-Store-Id is sent only when a store is configured. Account-level tokens
require it on every store-scoped endpoint; store-level tokens carry their own
context and must not send it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import TOKEN_HELP, PrintfulAuthError

CONFIG_DIR = Path.home() / ".config" / "printful"
CONFIG_FILE = CONFIG_DIR / "config.json"

ENV_API_KEY = "PRINTFUL_API_KEY"
ENV_STORE_ID = "PRINTFUL_STORE_ID"


def load_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, IOError):
        return {}


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as handle:
        json.dump(config, handle, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


@dataclass(frozen=True)
class Credentials:
    api_key: str
    store_id: Optional[str] = None

    @classmethod
    def resolve(cls, api_key: Optional[str] = None,
                store_id: Optional[Any] = None) -> "Credentials":
        """Resolve credentials: explicit argument, then environment, then config."""
        config = load_config()

        key = api_key or os.environ.get(ENV_API_KEY) or config.get("api_key")
        if not key:
            raise PrintfulAuthError(
                "No Printful API token configured.\n" + TOKEN_HELP, status_code=401
            )

        store = store_id or os.environ.get(ENV_STORE_ID) or config.get("store_id")
        return cls(api_key=key, store_id=str(store) if store else None)

    def headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.store_id:
            headers["X-PF-Store-Id"] = self.store_id
        if extra:
            headers.update(extra)
        return headers
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_auth.py -v -o addopts=""
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/printful_core/auth.py src/printful_core/tests/test_auth.py
git commit -m "feat: resolve credentials and headers in the core

Precedence is explicit argument, environment, then config file. X-PF-Store-Id
is emitted only when a store is configured, which is what account-level tokens
need and what store-level tokens must not send."
```

---

## Task 7: Synchronous and asynchronous transports

**Files:**
- Create: `src/printful_core/transport.py`, `src/printful_core/tests/test_transport.py`
- Modify: `pyproject.toml` (drop `requests`)

**Interfaces:**
- Consumes: `Request`, `Credentials`, `raise_for_status`
- Produces: `SyncTransport(credentials, timeout=30.0)` with `.send(Request) -> dict` and `.close()`; `AsyncTransport` with `async .send(Request) -> dict` and `async .close()`; `BASE_URLS`

- [ ] **Step 1: Write the failing test**

Create `src/printful_core/tests/test_transport.py`:

```python
import pytest

from printful_core.auth import Credentials
from printful_core.errors import PrintfulError, PrintfulRateLimitError
from printful_core.request import Request
from printful_core.transport import AsyncTransport, SyncTransport


class FakeHTTPResponse:
    def __init__(self, status_code=200, body=None, headers=None, text="x"):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._body is _INVALID:
            raise ValueError("not json")
        return self._body


_INVALID = object()


class FakeHTTPClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

    def close(self):
        pass


def make_sync(responses, store_id=None):
    transport = SyncTransport(Credentials("tok", store_id))
    transport.client = FakeHTTPClient(responses)
    return transport


class TestUrlAndHeaders:
    def test_v2_base_url(self):
        t = make_sync([FakeHTTPResponse(200, {"data": []})])
        t.send(Request("GET", "/countries"))
        assert t.client.calls[0]["url"] == "https://api.printful.com/v2/countries"

    def test_v1_base_url(self):
        t = make_sync([FakeHTTPResponse(200, {"code": 200, "result": []})])
        t.send(Request("GET", "/store/products", version="v1"))
        assert t.client.calls[0]["url"] == "https://api.printful.com/store/products"

    def test_authorization_header(self):
        t = make_sync([FakeHTTPResponse(200, {"data": []})])
        t.send(Request("GET", "/countries"))
        assert t.client.calls[0]["headers"]["Authorization"] == "Bearer tok"

    def test_store_header_when_configured(self):
        t = make_sync([FakeHTTPResponse(200, {"data": []})], store_id="777")
        t.send(Request("GET", "/orders"))
        assert t.client.calls[0]["headers"]["X-PF-Store-Id"] == "777"


class TestResponseNormalization:
    def test_v2_body_unchanged(self):
        t = make_sync([FakeHTTPResponse(200, {"data": {"id": 1}})])
        assert t.send(Request("GET", "/orders/1")) == {"data": {"id": 1}}

    def test_v1_unwraps_result(self):
        t = make_sync([FakeHTTPResponse(200, {"code": 200, "result": [{"id": 9}]})])
        assert t.send(Request("GET", "/store/products", version="v1")) == [{"id": 9}]

    def test_204_returns_empty_dict(self):
        t = make_sync([FakeHTTPResponse(204, {}, text="")])
        assert t.send(Request("DELETE", "/orders/1")) == {}

    def test_invalid_json_raises(self):
        t = make_sync([FakeHTTPResponse(200, _INVALID)])
        with pytest.raises(PrintfulError, match="Invalid JSON"):
            t.send(Request("GET", "/x"))


class TestErrors:
    def test_error_message_surfaces(self):
        body = {"data": "nope", "error": {"reason": "BadRequest", "message": "nope"}}
        t = make_sync([FakeHTTPResponse(400, body)])
        with pytest.raises(PrintfulError, match="nope"):
            t.send(Request("GET", "/x"))

    def test_rate_limit(self):
        t = make_sync([FakeHTTPResponse(429, {}, headers={"Retry-After": "12"})])
        with pytest.raises(PrintfulRateLimitError) as exc:
            t.send(Request("GET", "/x"))
        assert exc.value.retry_after == "12"


@pytest.mark.asyncio
async def test_async_transport_shares_behavior():
    class FakeAsyncClient:
        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = []

        async def request(self, **kwargs):
            self.calls.append(kwargs)
            return self.responses.pop(0)

        async def aclose(self):
            pass

    transport = AsyncTransport(Credentials("tok", None))
    transport.client = FakeAsyncClient([FakeHTTPResponse(200, {"data": [1]})])
    assert await transport.send(Request("GET", "/countries")) == {"data": [1]}
    assert transport.client.calls[0]["url"].endswith("/v2/countries")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_transport.py -v \
    -o asyncio_mode=auto -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'printful_core.transport'`

- [ ] **Step 3: Write the implementation**

Create `src/printful_core/transport.py`:

```python
"""Executes a Request. The only module in the core that touches the network.

httpx ships Client and AsyncClient with matching APIs, so one module serves the
synchronous CLI and the asynchronous MCP server without duplicating URL
construction, header handling, or response normalization.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .auth import Credentials
from .errors import PrintfulError, raise_for_status
from .request import Request

BASE_URLS = {
    "v2": "https://api.printful.com/v2",
    "v1": "https://api.printful.com",
}

DEFAULT_TIMEOUT = 30.0


def _url(request: Request) -> str:
    return f"{BASE_URLS[request.version]}{request.path}"


def _normalize(request: Request, response) -> Dict[str, Any]:
    """Turn a successful response into a body, or raise for a failure."""
    if 200 <= response.status_code < 300:
        if response.status_code == 204 or not response.text:
            return {}
        try:
            body = response.json()
        except ValueError:
            raise PrintfulError(
                f"Invalid JSON in response from {_url(request)} "
                f"(status {response.status_code})",
                status_code=response.status_code,
            )
        if request.version == "v2":
            return body
        # v1 wraps its payload in {"code": ..., "result": ...}
        return body.get("result", body) if isinstance(body, dict) else body

    try:
        body = response.json()
    except ValueError:
        body = response.text

    raise_for_status(response.status_code, body, _url(request),
                     headers=response.headers)


class SyncTransport:
    """Executes requests synchronously. Used by the CLI."""

    def __init__(self, credentials: Credentials, timeout: float = DEFAULT_TIMEOUT):
        self.credentials = credentials
        self.client = httpx.Client(timeout=timeout)

    def send(self, request: Request,
             extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        try:
            response = self.client.request(
                method=request.method,
                url=_url(request),
                params=request.params or None,
                json=request.json,
                headers=self.credentials.headers(extra_headers),
            )
        except httpx.TimeoutException:
            raise PrintfulError(f"Request to {_url(request)} timed out.")
        except httpx.RequestError as exc:
            raise PrintfulError(f"Request error: {exc}")
        return _normalize(request, response)

    def close(self) -> None:
        self.client.close()


class AsyncTransport:
    """Executes requests asynchronously. Used by the MCP server."""

    def __init__(self, credentials: Credentials, timeout: float = DEFAULT_TIMEOUT):
        self.credentials = credentials
        self.client = httpx.AsyncClient(timeout=timeout)

    async def send(self, request: Request,
                   extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        try:
            response = await self.client.request(
                method=request.method,
                url=_url(request),
                params=request.params or None,
                json=request.json,
                headers=self.credentials.headers(extra_headers),
            )
        except httpx.TimeoutException:
            raise PrintfulError(f"Request to {_url(request)} timed out.")
        except httpx.RequestError as exc:
            raise PrintfulError(f"Request error: {exc}")
        return _normalize(request, response)

    async def close(self) -> None:
        await self.client.aclose()
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_transport.py -v \
    -o asyncio_mode=auto -o addopts=""
```

Expected: 11 passed.

- [ ] **Step 5: Set asyncio mode permanently**

In `pyproject.toml`, under `[tool.pytest.ini_options]`, add:

```toml
asyncio_mode = "auto"
```

- [ ] **Step 6: Run the whole suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: all pass, no errors about async functions.

- [ ] **Step 7: Commit**

```bash
git add src/printful_core/transport.py src/printful_core/tests/test_transport.py \
        pyproject.toml
git commit -m "feat: add synchronous and asynchronous transports

httpx ships Client and AsyncClient with matching APIs, so URL construction,
header handling, and response normalization are written once and shared by the
CLI and the MCP server."
```

---

## Task 8: Generic pagination

`/v2/countries` returns 20 of 239 rows by default and `US` falls outside the first page, so a single request reports that Printful does not ship to the United States. Solving it per-endpoint invites the same defect elsewhere.

**Files:**
- Create: `src/printful_core/pagination.py`, `src/printful_core/tests/test_pagination.py`

**Interfaces:**
- Consumes: `Request`
- Produces: `PAGE_LIMIT = 100`, `collect_pages(request, send) -> dict`

- [ ] **Step 1: Write the failing test**

Create `src/printful_core/tests/test_pagination.py`:

```python
from printful_core.pagination import PAGE_LIMIT, collect_pages
from printful_core.request import Request


def make_sender(pages):
    sent = []

    def send(request):
        sent.append(request)
        return pages.pop(0)

    send.sent = sent
    return send


def test_walks_every_page():
    send = make_sender([
        {"data": [{"code": "AF"}, {"code": "AL"}],
         "paging": {"total": 5, "limit": 2, "offset": 0}},
        {"data": [{"code": "DE"}, {"code": "GB"}],
         "paging": {"total": 5, "limit": 2, "offset": 2}},
        {"data": [{"code": "US"}],
         "paging": {"total": 5, "limit": 2, "offset": 4}},
    ])
    result = collect_pages(Request("GET", "/countries"), send)
    assert [row["code"] for row in result["data"]] == ["AF", "AL", "DE", "GB", "US"]
    assert result["paging"]["returned"] == 5
    assert len(send.sent) == 3


def test_offset_advances_on_each_request():
    send = make_sender([
        {"data": [1, 2], "paging": {"total": 4, "limit": 2, "offset": 0}},
        {"data": [3, 4], "paging": {"total": 4, "limit": 2, "offset": 2}},
    ])
    collect_pages(Request("GET", "/countries"), send)
    assert send.sent[1].params["offset"] == 2


def test_first_request_uses_page_limit():
    send = make_sender([{"data": [], "paging": {"total": 0, "limit": 100, "offset": 0}}])
    collect_pages(Request("GET", "/countries"), send)
    assert send.sent[0].params["limit"] == PAGE_LIMIT


def test_missing_paging_returns_first_page():
    send = make_sender([{"data": [{"code": "US"}]}])
    assert len(collect_pages(Request("GET", "/countries"), send)["data"]) == 1


def test_empty_page_stops_the_loop():
    send = make_sender([
        {"data": [{"code": "AF"}], "paging": {"total": 99, "limit": 1, "offset": 0}},
        {"data": [], "paging": {"total": 99, "limit": 1, "offset": 1}},
    ])
    assert len(collect_pages(Request("GET", "/countries"), send)["data"]) == 1


def test_single_page_needs_one_request():
    send = make_sender([{"data": [1], "paging": {"total": 1, "limit": 100, "offset": 0}}])
    collect_pages(Request("GET", "/countries"), send)
    assert len(send.sent) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_pagination.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'printful_core.pagination'`

- [ ] **Step 3: Write the implementation**

Create `src/printful_core/pagination.py`:

```python
"""Walk every page of a paginated Printful collection.

/v2/countries defaults to 20 of 239 rows and 'US' is not in the first page
alphabetically, so a single request answers "does Printful ship to the US?"
with no. Pagination belongs here rather than in each endpoint, so the defect
cannot recur one endpoint at a time.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from .request import Request

PAGE_LIMIT = 100


def collect_pages(request: Request,
                  send: Callable[[Request], Dict[str, Any]]) -> Dict[str, Any]:
    """Send `request` and every following page, merging their rows."""
    first = send(request.with_params(limit=PAGE_LIMIT, offset=0))

    rows = list(first.get("data", []) or [])
    paging = first.get("paging") or {}
    total = paging.get("total")
    limit = paging.get("limit") or PAGE_LIMIT

    if not isinstance(total, int):
        return first

    offset = len(rows)
    while offset < total:
        page = send(request.with_params(limit=limit, offset=offset))
        batch = page.get("data", []) or []
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)

    merged = dict(first)
    merged["data"] = rows
    merged["paging"] = {"total": total, "limit": limit, "offset": 0,
                        "returned": len(rows)}
    return merged
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_pagination.py -v -o addopts=""
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/printful_core/pagination.py src/printful_core/tests/test_pagination.py
git commit -m "feat: walk paginated collections generically

/v2/countries returns 20 of 239 rows by default and US is not on the first
page, so a single request reports that Printful does not ship to the US.
Handling pagination centrally stops that defect recurring per endpoint."
```

---

## Task 9: Catalog and shipping endpoint builders

**Files:**
- Create: `src/printful_core/endpoints/__init__.py`, `src/printful_core/endpoints/catalog.py`, `src/printful_core/endpoints/shipping.py`
- Create: `src/printful_core/tests/test_endpoints_catalog.py`, `src/printful_core/tests/test_endpoints_shipping.py`

**Interfaces:**
- Consumes: `Request`
- Produces: `catalog.list_products`, `catalog.get_product`, `catalog.list_variants`, `catalog.get_variant_prices`, `catalog.get_availability`, `catalog.list_categories`, `catalog.get_category`, `catalog.get_size_guide`; `shipping.calculate_rates`, `shipping.list_countries`, `shipping.calculate_tax` — each returning `Request`

- [ ] **Step 1: Write the failing tests**

Create `src/printful_core/tests/test_endpoints_catalog.py`:

```python
import pytest

from printful_core.endpoints import catalog


def test_list_products_path_and_defaults():
    req = catalog.list_products()
    assert req.method == "GET"
    assert req.path == "/catalog-products"
    assert req.params == {"limit": 20, "offset": 0}


def test_list_products_drops_unset_filters():
    req = catalog.list_products(limit=5, colors="black")
    assert req.params == {"limit": 5, "offset": 0, "colors": "black"}


def test_get_product_path():
    assert catalog.get_product(71).path == "/catalog-products/71"


def test_list_variants_path():
    assert catalog.list_variants(71).path == "/catalog-products/71/catalog-variants"


def test_variant_prices_path():
    assert catalog.get_variant_prices(4012).path == "/catalog-variants/4012/prices"


def test_availability_path():
    assert catalog.get_availability(71).path == "/catalog-products/71/availability"


def test_categories_path():
    assert catalog.list_categories().path == "/catalog-categories"


def test_category_path():
    assert catalog.get_category(24).path == "/catalog-categories/24"


def test_size_guide_path():
    assert catalog.get_size_guide(71).path == "/catalog-products/71/sizes"


def test_size_guide_unit_passed_through():
    assert catalog.get_size_guide(71, unit="cm").params == {"unit": "cm"}
```

Create `src/printful_core/tests/test_endpoints_shipping.py`:

```python
import pytest

from printful_core.endpoints import shipping

RECIPIENT = {"country_code": "US", "state_code": "NC", "zip": "28273"}


def test_countries_path():
    assert shipping.list_countries().path == "/countries"


def test_rates_path_and_method():
    req = shipping.calculate_rates(RECIPIENT,
                                   [{"catalog_variant_id": 4012, "quantity": 1}])
    assert req.method == "POST"
    assert req.path == "/shipping-rates"


def test_rates_default_missing_source():
    """The live API rejects an item without source: 'must be of type string'."""
    req = shipping.calculate_rates(RECIPIENT,
                                   [{"catalog_variant_id": 4012, "quantity": 1}])
    assert req.json["order_items"][0]["source"] == "catalog"


def test_rates_preserve_explicit_source():
    req = shipping.calculate_rates(
        RECIPIENT, [{"source": "sync_product", "catalog_variant_id": 1, "quantity": 1}]
    )
    assert req.json["order_items"][0]["source"] == "sync_product"


def test_rates_do_not_mutate_caller_items():
    items = [{"catalog_variant_id": 4012, "quantity": 1}]
    shipping.calculate_rates(RECIPIENT, items)
    assert "source" not in items[0]


def test_rates_reject_empty_items():
    with pytest.raises(ValueError, match="at least one item"):
        shipping.calculate_rates(RECIPIENT, [])


def test_tax_uses_v1():
    req = shipping.calculate_tax("US", state_code="CA", zip_code="90001")
    assert req.version == "v1"
    assert req.path == "/tax/rates"
    assert req.json["recipient"]["state_code"] == "CA"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_endpoints_catalog.py \
    src/printful_core/tests/test_endpoints_shipping.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'printful_core.endpoints'`

- [ ] **Step 3: Write the catalog builders**

Create `src/printful_core/endpoints/__init__.py`:

```python
"""Pure request builders. Nothing in this package performs I/O."""
```

Create `src/printful_core/endpoints/catalog.py`:

```python
"""Catalog endpoints (v2)."""
from __future__ import annotations

from typing import Optional

from ..request import Request


def list_products(limit: int = 20, offset: int = 0,
                  category_ids: Optional[str] = None,
                  colors: Optional[str] = None,
                  techniques: Optional[str] = None,
                  types: Optional[str] = None) -> Request:
    return Request("GET", "/catalog-products", params={
        "limit": limit, "offset": offset, "category_ids": category_ids,
        "colors": colors, "techniques": techniques, "types": types,
    })


def get_product(product_id: int) -> Request:
    return Request("GET", f"/catalog-products/{product_id}")


def list_variants(product_id: int, limit: int = 20, offset: int = 0) -> Request:
    return Request("GET", f"/catalog-products/{product_id}/catalog-variants",
                   params={"limit": limit, "offset": offset})


def get_variant_prices(variant_id: int, currency: Optional[str] = None) -> Request:
    return Request("GET", f"/catalog-variants/{variant_id}/prices",
                   params={"currency": currency})


def get_availability(product_id: int, techniques: Optional[str] = None) -> Request:
    return Request("GET", f"/catalog-products/{product_id}/availability",
                   params={"techniques": techniques})


def list_categories(limit: int = 20, offset: int = 0) -> Request:
    return Request("GET", "/catalog-categories",
                   params={"limit": limit, "offset": offset})


def get_category(category_id: int) -> Request:
    return Request("GET", f"/catalog-categories/{category_id}")


def get_size_guide(product_id: int, unit: Optional[str] = None) -> Request:
    return Request("GET", f"/catalog-products/{product_id}/sizes",
                   params={"unit": unit})
```

- [ ] **Step 4: Write the shipping builders**

Create `src/printful_core/endpoints/shipping.py`:

```python
"""Shipping rates and countries (v2); tax rates (v1 only)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..request import Request


def list_countries() -> Request:
    """Paginated. Pass the result through pagination.collect_pages."""
    return Request("GET", "/countries")


def calculate_rates(recipient: Dict[str, Any], items: List[Dict[str, Any]],
                    currency: Optional[str] = None,
                    locale: Optional[str] = None) -> Request:
    """Live shipping rates. Artwork is not required to quote a rate."""
    if not items:
        raise ValueError("Shipping rate calculation requires at least one item.")

    # The endpoint rejects an item without `source`: "Property
    # /order_items/0/source must be of type `string`, `null` provided".
    normalized = [{**item, "source": item.get("source") or "catalog"}
                  for item in items]

    body: Dict[str, Any] = {"recipient": recipient, "order_items": normalized}
    if currency:
        body["currency"] = currency
    if locale:
        body["locale"] = locale
    return Request("POST", "/shipping-rates", json=body)


def calculate_tax(country_code: str, state_code: Optional[str] = None,
                  city: Optional[str] = None,
                  zip_code: Optional[str] = None) -> Request:
    """Tax rate. v1 only — v2 exposes no tax endpoint."""
    recipient: Dict[str, Any] = {"country_code": country_code}
    if state_code:
        recipient["state_code"] = state_code
    if city:
        recipient["city"] = city
    if zip_code:
        recipient["zip"] = zip_code
    return Request("POST", "/tax/rates", version="v1",
                   json={"recipient": recipient})
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_endpoints_catalog.py \
    src/printful_core/tests/test_endpoints_shipping.py -v -o addopts=""
```

Expected: 17 passed.

- [ ] **Step 6: Commit**

```bash
git add src/printful_core/endpoints src/printful_core/tests/test_endpoints_catalog.py \
        src/printful_core/tests/test_endpoints_shipping.py
git commit -m "feat: add catalog and shipping request builders

Each operation returns a Request and performs no I/O, so paths and payload
shapes are asserted without a network call. calculate_rates defaults a missing
item source, which the live endpoint rejects."
```

---

## Task 10: Order endpoint builders

**Files:**
- Create: `src/printful_core/endpoints/orders.py`, `src/printful_core/tests/test_endpoints_orders.py`

**Interfaces:**
- Consumes: `Request`
- Produces: `orders.list_orders`, `get_order`, `create_order`, `update_order`, `cancel_order`, `confirm_order`, `list_items`, `list_shipments`, `create_estimation_task`, `get_estimation_task`, `build_catalog_item`

- [ ] **Step 1: Write the failing test**

Create `src/printful_core/tests/test_endpoints_orders.py`:

```python
import pytest

from printful_core.endpoints import orders

ITEM = {"source": "catalog", "catalog_variant_id": 4012, "quantity": 1,
        "placements": [{"placement": "front", "technique": "dtg",
                        "layers": [{"type": "file", "url": "https://x/a.png"}]}]}
RECIPIENT = {"name": "Jane", "address1": "1 St", "city": "Charlotte",
             "state_code": "NC", "country_code": "US", "zip": "28273"}


def test_list_orders_path():
    req = orders.list_orders()
    assert req.path == "/orders"
    assert req.params == {"limit": 20, "offset": 0}


def test_get_order_path():
    assert orders.get_order("123").path == "/orders/123"


def test_external_id_prefix_preserved():
    assert orders.get_order("@ext-1").path == "/orders/@ext-1"


def test_create_order_body():
    req = orders.create_order(RECIPIENT, [ITEM])
    assert req.method == "POST"
    assert req.path == "/orders"
    assert req.json["order_items"] == [ITEM]


def test_create_order_rejects_empty_items():
    with pytest.raises(ValueError, match="at least one item"):
        orders.create_order(RECIPIENT, [])


def test_create_order_rejects_catalog_item_without_placements():
    """Live API: 'Property `placements` is required'."""
    with pytest.raises(ValueError, match="placements"):
        orders.create_order(RECIPIENT, [{"source": "catalog",
                                         "catalog_variant_id": 1, "quantity": 1}])


def test_non_catalog_item_needs_no_placements():
    item = {"source": "sync_product", "sync_variant_id": 5, "quantity": 1}
    assert orders.create_order(RECIPIENT, [item]).json["order_items"] == [item]


def test_update_order_is_a_patch():
    req = orders.update_order("1", {"shipping": "STANDARD"})
    assert req.method == "PATCH"
    assert req.path == "/orders/1"


def test_update_rejects_empty_payload():
    with pytest.raises(ValueError, match="at least one field"):
        orders.update_order("1", {})


def test_cancel_order_is_a_delete():
    req = orders.cancel_order("1")
    assert req.method == "DELETE"
    assert req.path == "/orders/1"


def test_confirm_order_targets_confirmation():
    """Billable. Asserted here so no test ever calls it for real."""
    req = orders.confirm_order("123")
    assert req.method == "POST"
    assert req.path == "/orders/123/confirmation"


def test_items_and_shipments_paths():
    assert orders.list_items("7").path == "/orders/7/order-items"
    assert orders.list_shipments("7").path == "/orders/7/shipments"


def test_estimation_task_paths():
    create = orders.create_estimation_task(RECIPIENT, [ITEM])
    assert create.method == "POST"
    assert create.path == "/order-estimation-tasks"
    poll = orders.get_estimation_task("abc")
    assert poll.method == "GET"
    assert poll.params == {"id": "abc"}


def test_build_catalog_item_shapes_placements():
    item = orders.build_catalog_item(4012, 2, image_url="https://x/a.png")
    assert item["source"] == "catalog"
    assert item["quantity"] == 2
    assert item["placements"][0]["layers"][0]["url"] == "https://x/a.png"


def test_build_catalog_item_rejects_zero_quantity():
    with pytest.raises(ValueError, match="quantity must be >= 1"):
        orders.build_catalog_item(4012, 0)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_endpoints_orders.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'printful_core.endpoints.orders'`

- [ ] **Step 3: Write the implementation**

Create `src/printful_core/endpoints/orders.py`:

```python
"""Order endpoints (v2).

confirm_order submits an order for fulfillment and charges the account. Every
caller must gate it behind an explicit confirmation from the operator.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..request import Request


def _require_placements(items: List[Dict[str, Any]]) -> None:
    """Printful rejects a catalog item with no artwork; fail before sending."""
    for index, item in enumerate(items):
        if item.get("source", "catalog") == "catalog" and not item.get("placements"):
            raise ValueError(
                f"order_items[{index}] (variant "
                f"{item.get('catalog_variant_id')}) has no placements. Printful "
                "rejects a catalog item with no artwork."
            )


def build_catalog_item(catalog_variant_id: int, quantity: int = 1,
                       image_url: Optional[str] = None,
                       placement: str = "front", technique: str = "dtg",
                       external_id: Optional[str] = None) -> Dict[str, Any]:
    """Build one catalog order item in the shape the live API accepts."""
    if quantity < 1:
        raise ValueError(f"quantity must be >= 1, got {quantity}")

    item: Dict[str, Any] = {
        "source": "catalog",
        "catalog_variant_id": int(catalog_variant_id),
        "quantity": int(quantity),
    }
    if external_id:
        item["external_id"] = external_id
    if image_url:
        item["placements"] = [{
            "placement": placement,
            "technique": technique,
            "layers": [{"type": "file", "url": image_url}],
        }]
    return item


def list_orders(limit: int = 20, offset: int = 0,
                status: Optional[str] = None) -> Request:
    return Request("GET", "/orders",
                   params={"limit": limit, "offset": offset, "status": status})


def get_order(order_id: str) -> Request:
    """Accepts an order ID, or an external ID prefixed with '@'."""
    return Request("GET", f"/orders/{order_id}")


def create_order(recipient: Dict[str, Any], items: List[Dict[str, Any]],
                 external_id: Optional[str] = None,
                 shipping: Optional[str] = None) -> Request:
    """Create a DRAFT order. Drafts are not charged until confirmed."""
    if not items:
        raise ValueError("Creating an order requires at least one item.")
    _require_placements(items)

    body: Dict[str, Any] = {"recipient": recipient, "order_items": items}
    if external_id:
        body["external_id"] = external_id
    if shipping:
        body["shipping"] = shipping
    return Request("POST", "/orders", json=body)


def update_order(order_id: str, changes: Dict[str, Any]) -> Request:
    if not changes:
        raise ValueError("Update requires at least one field to change.")
    return Request("PATCH", f"/orders/{order_id}", json=changes)


def cancel_order(order_id: str) -> Request:
    """Destructive. Callers must require explicit confirmation."""
    return Request("DELETE", f"/orders/{order_id}")


def confirm_order(order_id: str) -> Request:
    """CHARGES THE ACCOUNT. Callers must require explicit confirmation."""
    return Request("POST", f"/orders/{order_id}/confirmation")


def list_items(order_id: str) -> Request:
    return Request("GET", f"/orders/{order_id}/order-items")


def list_shipments(order_id: str) -> Request:
    return Request("GET", f"/orders/{order_id}/shipments")


def create_estimation_task(recipient: Dict[str, Any],
                           items: List[Dict[str, Any]]) -> Request:
    """Start an asynchronous cost estimate. Free; places no order."""
    if not items:
        raise ValueError("Estimation requires at least one item.")
    return Request("POST", "/order-estimation-tasks",
                   json={"recipient": recipient, "order_items": items})


def get_estimation_task(task_id: str) -> Request:
    return Request("GET", "/order-estimation-tasks", params={"id": task_id})
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_endpoints_orders.py -v -o addopts=""
```

Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add src/printful_core/endpoints/orders.py \
        src/printful_core/tests/test_endpoints_orders.py
git commit -m "feat: add order request builders

create_order rejects a catalog item with no placements before sending, which
is what the live API requires and what the previous implementation omitted.
confirm_order's path is asserted against a builder so no test ever has to call
the billable endpoint."
```

---

## Task 11: Remaining endpoint builders

**Files:**
- Create: `src/printful_core/endpoints/mockups.py`, `files.py`, `stores.py`, `sync.py`
- Create: `src/printful_core/tests/test_endpoints_remaining.py`

**Interfaces:**
- Consumes: `Request`
- Produces: `mockups.create_task`, `mockups.get_task`, `mockups.list_styles`, `mockups.list_templates`; `files.add_file`, `files.get_file`; `stores.list_stores`, `stores.get_statistics`, `stores.list_templates`; `sync.list_products`, `sync.get_product`

- [ ] **Step 1: Write the failing test**

Create `src/printful_core/tests/test_endpoints_remaining.py`:

```python
import pytest

from printful_core.endpoints import files, mockups, stores, sync


class TestMockups:
    def test_create_task_path_and_payload(self):
        req = mockups.create_task(71, [4012], "https://x/a.png")
        assert req.method == "POST"
        assert req.path == "/mockup-tasks"
        product = req.json["products"][0]
        assert product["catalog_product_id"] == 71
        assert product["catalog_variant_ids"] == [4012]
        assert product["placements"][0]["layers"][0]["url"] == "https://x/a.png"

    def test_create_task_includes_style_ids_when_given(self):
        req = mockups.create_task(71, [4012], "https://x/a.png", style_ids=[5, 6])
        assert req.json["products"][0]["mockup_style_ids"] == [5, 6]

    def test_create_task_rejects_empty_variants(self):
        with pytest.raises(ValueError, match="variant ID"):
            mockups.create_task(71, [], "https://x/a.png")

    def test_create_task_rejects_missing_image(self):
        with pytest.raises(ValueError, match="image URL"):
            mockups.create_task(71, [4012], "")

    def test_get_task_uses_id_param(self):
        assert mockups.get_task("t1").params == {"id": "t1"}

    def test_styles_and_templates_paths(self):
        assert mockups.list_styles(71).path == "/catalog-products/71/mockup-styles"
        assert mockups.list_templates(71).path == "/catalog-products/71/mockup-templates"


class TestFiles:
    def test_add_file_payload(self):
        req = files.add_file("https://x/a.png", filename="a.png")
        assert req.method == "POST"
        assert req.path == "/files"
        assert req.json == {"url": "https://x/a.png", "visible": True,
                            "filename": "a.png"}

    def test_add_file_rejects_empty_url(self):
        with pytest.raises(ValueError, match="URL is required"):
            files.add_file("")

    def test_get_file_path(self):
        assert files.get_file(5).path == "/files/5"


class TestStores:
    def test_list_path(self):
        assert stores.list_stores().path == "/stores"

    def test_statistics_path_and_params(self):
        req = stores.get_statistics(1135966, "2026-01-01", "2026-03-01")
        assert req.path == "/stores/1135966/statistics"
        assert req.params["date_from"] == "2026-01-01"
        assert req.params["report_types"] == "sales_and_costs,profit"

    def test_templates_use_v1(self):
        req = stores.list_templates()
        assert req.version == "v1"
        assert req.path == "/product-templates"


class TestSync:
    def test_list_uses_v1(self):
        req = sync.list_products()
        assert req.version == "v1"
        assert req.path == "/store/products"

    def test_get_uses_v1(self):
        assert sync.get_product(9).path == "/store/products/9"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_endpoints_remaining.py -v -o addopts=""
```

Expected: `ImportError: cannot import name 'files' from 'printful_core.endpoints'`

- [ ] **Step 3: Write the four modules**

Create `src/printful_core/endpoints/mockups.py`:

```python
"""Mockup generator endpoints (v2).

Mockup creation is the most tightly limited part of the API: 10 requests/60s
for established stores, 2/60s for new stores, a 60-second lockout on exceeding
it, and 20,000 generated files per account per 24 hours.
"""
from __future__ import annotations

from typing import List, Optional

from ..request import Request

RATE_LIMIT_NOTE = (
    "Mockup creation is limited to 10 requests/60s (established stores) or "
    "2 requests/60s (new stores), with a 60s lockout when exceeded."
)


def create_task(product_id: int, variant_ids: List[int], image_url: str,
                placement: str = "front", technique: str = "dtg",
                style_ids: Optional[List[int]] = None,
                image_format: str = "jpg") -> Request:
    if not variant_ids:
        raise ValueError("At least one catalog variant ID is required.")
    if not image_url:
        raise ValueError("A design image URL is required.")

    product = {
        "source": "catalog",
        "catalog_product_id": int(product_id),
        "catalog_variant_ids": [int(v) for v in variant_ids],
        "orientation": "any",
        "placements": [{
            "placement": placement,
            "technique": technique,
            "layers": [{"type": "file", "url": image_url}],
        }],
    }
    if style_ids:
        product["mockup_style_ids"] = [int(s) for s in style_ids]

    return Request("POST", "/mockup-tasks",
                   json={"format": image_format, "products": [product]})


def get_task(task_id: str) -> Request:
    return Request("GET", "/mockup-tasks", params={"id": task_id})


def list_styles(product_id: int) -> Request:
    return Request("GET", f"/catalog-products/{product_id}/mockup-styles")


def list_templates(product_id: int) -> Request:
    return Request("GET", f"/catalog-products/{product_id}/mockup-templates")
```

Create `src/printful_core/endpoints/files.py`:

```python
"""File library endpoints (v2).

Printful exposes only "add a file" and "get a file by ID". Neither API version
has a list-files endpoint, so any listing must come from a caller's own record.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..request import Request


def add_file(url: str, filename: Optional[str] = None,
             visible: bool = True) -> Request:
    if not url:
        raise ValueError("A file URL is required.")
    body: Dict[str, Any] = {"url": url, "visible": visible}
    if filename:
        body["filename"] = filename
    return Request("POST", "/files", json=body)


def get_file(file_id: int) -> Request:
    return Request("GET", f"/files/{file_id}")
```

Create `src/printful_core/endpoints/stores.py`:

```python
"""Store endpoints. Stores and statistics are v2; product templates are v1."""
from __future__ import annotations

from typing import Optional

from ..request import Request


def list_stores() -> Request:
    return Request("GET", "/stores")


def get_statistics(store_id: int, date_from: str, date_to: str,
                   report_types: str = "sales_and_costs,profit",
                   currency: Optional[str] = None) -> Request:
    """Store statistics. Printful caps the range at six months."""
    return Request("GET", f"/stores/{store_id}/statistics", params={
        "date_from": date_from, "date_to": date_to,
        "report_types": report_types, "currency": currency,
    })


def list_templates(limit: int = 20, offset: int = 0) -> Request:
    """Product templates. v1 only — v2 exposes no equivalent."""
    return Request("GET", "/product-templates", version="v1",
                   params={"limit": limit, "offset": offset})
```

Create `src/printful_core/endpoints/sync.py`:

```python
"""Sync product endpoints. v1 only — not yet available in v2."""
from __future__ import annotations

from ..request import Request


def list_products(limit: int = 20, offset: int = 0) -> Request:
    return Request("GET", "/store/products", version="v1",
                   params={"limit": limit, "offset": offset})


def get_product(sync_product_id: int) -> Request:
    return Request("GET", f"/store/products/{sync_product_id}", version="v1")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_endpoints_remaining.py -v -o addopts=""
```

Expected: 15 passed.

- [ ] **Step 5: Run the whole core suite**

```bash
.venv/bin/python -m pytest src/printful_core -q
```

Expected: all pass. 93 tests (5 request, 15 errors, 9 auth, 11 transport,
6 pagination, 10 catalog, 7 shipping, 15 orders, 15 remaining).

- [ ] **Step 6: Commit**

```bash
git add src/printful_core/endpoints src/printful_core/tests/test_endpoints_remaining.py
git commit -m "feat: add mockup, file, store, and sync request builders

Completes the endpoint layer. Every Printful operation the project supports now
has one pure builder, tested without a network call."
```

---

## Task 12: Move response formatters into the core

**Files:**
- Create: `src/printful_core/format/__init__.py`, `src/printful_core/format/summary.py`
- Create: `src/printful_core/tests/test_format.py`
- Read for reference: `src/cli_anything/printful/core/catalog.py`, `shipping.py`, `orders.py`, `stores.py` (their `summarize_*` functions)

**Interfaces:**
- Consumes: nothing
- Produces: `summary.products`, `summary.variants`, `summary.orders`, `summary.rates`, `summary.countries`, `summary.stores`, `summary.mockup_urls`

- [ ] **Step 1: Write the failing test**

Create `src/printful_core/tests/test_format.py`:

```python
from printful_core.format import summary


class TestProducts:
    def test_empty(self):
        assert summary.products({})["count"] == 0

    def test_partial_payload_does_not_raise(self):
        out = summary.products({"data": [{"id": 1, "name": "Tee"}]})
        assert out["products"][0]["type"] is None
        assert out["products"][0]["techniques"] == ""

    def test_techniques_joined(self):
        out = summary.products({"data": [
            {"id": 1, "name": "Tee", "techniques": [{"key": "dtg"}, {"key": "emb"}]}
        ]})
        assert out["products"][0]["techniques"] == "dtg,emb"


class TestRates:
    def test_live_keys(self):
        """Live rows are keyed shipping / shipping_method_name, not id / name."""
        row = summary.rates({"data": [{
            "shipping": "STANDARD",
            "shipping_method_name": "Flat Rate",
            "rate": "4.95", "currency": "USD",
            "min_delivery_days": 4, "max_delivery_days": 6,
        }]})["rates"][0]
        assert row["id"] == "STANDARD"
        assert row["name"] == "Flat Rate"
        assert row["rate"] == "4.95"

    def test_falls_back_to_id_and_name(self):
        row = summary.rates({"data": [{"id": "X", "name": "Legacy",
                                       "rate": "1.00"}]})["rates"][0]
        assert row["id"] == "X"
        assert row["name"] == "Legacy"

    def test_empty(self):
        assert summary.rates({})["count"] == 0


class TestCountries:
    def test_counts_states(self):
        out = summary.countries({"data": [{"code": "US", "name": "United States",
                                           "states": [1, 2]}]})
        assert out["countries"][0]["states"] == 2

    def test_missing_states_key(self):
        assert summary.countries({"data": [{"code": "DE"}]})["countries"][0]["states"] == 0


class TestOrders:
    def test_missing_costs(self):
        out = summary.orders({"data": [{"id": 1, "status": "draft"}]})
        assert out["orders"][0]["total"] is None
        assert out["count"] == 1


class TestMockupUrls:
    def test_primary_and_extra(self):
        data = {"data": [{"mockups": [
            {"mockup_url": "https://x/1.jpg", "extra": [{"url": "https://x/2.jpg"}]}
        ]}]}
        assert summary.mockup_urls(data) == ["https://x/1.jpg", "https://x/2.jpg"]

    def test_empty_and_malformed(self):
        assert summary.mockup_urls({}) == []
        assert summary.mockup_urls({"data": ["junk"]}) == []


class TestVariantsAndStores:
    def test_variants_empty(self):
        assert summary.variants({})["count"] == 0

    def test_stores(self):
        out = summary.stores({"data": [{"id": 1, "name": "A", "type": "native"}]})
        assert out["stores"][0]["name"] == "A"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_format.py -v -o addopts=""
```

Expected: `ModuleNotFoundError: No module named 'printful_core.format'`

- [ ] **Step 3: Write the implementation**

Create `src/printful_core/format/__init__.py`:

```python
"""Response formatting shared by both surfaces."""

from . import summary  # noqa: F401
```

Create `src/printful_core/format/summary.py`:

```python
"""Flatten API responses into table-friendly rows.

Field names come from live responses, not the documentation. Shipping rates in
particular are keyed `shipping` and `shipping_method_name`; reading `id` and
`name` yields a table of nulls.
"""
from __future__ import annotations

from typing import Any, Dict, List


def products(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    for product in data.get("data", []) or []:
        techniques = product.get("techniques") or []
        rows.append({
            "id": product.get("id"),
            "name": product.get("name"),
            "type": product.get("type"),
            "brand": product.get("brand"),
            "variants": product.get("variant_count"),
            "techniques": ",".join(t.get("key", "") for t in techniques
                                   if isinstance(t, dict)),
        })
    return {"products": rows, "paging": data.get("paging", {}), "count": len(rows)}


def variants(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{
        "id": v.get("id"), "name": v.get("name"),
        "size": v.get("size"), "color": v.get("color"),
    } for v in data.get("data", []) or []]
    return {"variants": rows, "paging": data.get("paging", {}), "count": len(rows)}


def orders(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    for order in data.get("data", []) or []:
        costs = order.get("costs") or {}
        rows.append({
            "id": order.get("id"),
            "external_id": order.get("external_id"),
            "status": order.get("status"),
            "created": order.get("created_at"),
            "total": costs.get("total"),
            "currency": costs.get("currency"),
        })
    return {"orders": rows, "paging": data.get("paging", {}), "count": len(rows)}


def rates(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{
        "id": r.get("shipping") or r.get("id"),
        "name": r.get("shipping_method_name") or r.get("name"),
        "rate": r.get("rate"),
        "currency": r.get("currency"),
        "min_days": r.get("min_delivery_days"),
        "max_days": r.get("max_delivery_days"),
        "min_date": r.get("min_delivery_date"),
        "max_date": r.get("max_delivery_date"),
    } for r in data.get("data", []) or []]
    return {"rates": rows, "count": len(rows)}


def countries(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{
        "code": c.get("code"), "name": c.get("name"),
        "states": len(c.get("states") or []),
    } for c in data.get("data", []) or []]
    return {"countries": rows, "count": len(rows)}


def stores(data: Dict[str, Any]) -> Dict[str, Any]:
    rows = [{
        "id": s.get("id"), "name": s.get("name"),
        "type": s.get("type"), "website": s.get("website"),
    } for s in data.get("data", []) or []]
    return {"stores": rows, "count": len(rows)}


def mockup_urls(data: Dict[str, Any]) -> List[str]:
    """Every mockup image URL in a completed task response."""
    body = data.get("data", data)
    if isinstance(body, dict):
        body = [body]

    urls: List[str] = []
    for task in body or []:
        if not isinstance(task, dict):
            continue
        for item in task.get("mockups", []) or []:
            url = item.get("mockup_url") or item.get("url")
            if url:
                urls.append(url)
            for extra in item.get("extra", []) or []:
                if extra.get("url"):
                    urls.append(extra["url"])
    return urls
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/python -m pytest src/printful_core/tests/test_format.py -v -o addopts=""
```

Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add src/printful_core/format src/printful_core/tests/test_format.py
git commit -m "feat: move response formatters into the core

Field names come from live responses. Shipping rate rows are keyed shipping
and shipping_method_name, so a formatter reading id and name renders nulls in
its two most important columns."
```

---

## Task 13: Rename the CLI package and drop the vendored skin

**Files:**
- Move: `src/cli_anything/printful/` → `src/printful_cli/`
- Delete: `src/printful_cli/utils/repl_skin.py`
- Create: `src/printful_cli/ui.py`
- Modify: `pyproject.toml`, every `from cli_anything.printful` import

**Interfaces:**
- Consumes: nothing from the core yet
- Produces: package `printful_cli`, console script `printful`, `ui.UI` with `.table(headers, rows)`, `.success/.error/.warning/.info(msg)`, `.section(title)`, `.status(label, value)`, `.prompt(text, count) -> int`

- [ ] **Step 1: Move the package and delete the vendored skin**

```bash
git mv src/cli_anything/printful src/printful_cli 2>/dev/null || \
    mv src/cli_anything/printful src/printful_cli
rmdir src/cli_anything 2>/dev/null || true
rm src/printful_cli/utils/repl_skin.py
```

- [ ] **Step 2: Rewrite the imports**

```bash
grep -rl 'cli_anything\.printful' src/ | xargs sed -i '' 's/cli_anything\.printful/printful_cli/g'
grep -rn 'cli_anything' src/ || echo "no references remain"
```

Expected: `no references remain`

- [ ] **Step 3: Write the replacement UI**

Create `src/printful_cli/ui.py`:

```python
"""Terminal output for the CLI.

Replaces the vendored cli-anything REPL skin. Colour is disabled when stdout is
not a terminal, so piped output stays parseable.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Sequence

import click

_ACCENT = "cyan"
_DIM = "bright_black"


class UI:
    """Human-facing output. Never used when --json is set."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout

    @property
    def colour(self) -> bool:
        return self.stream.isatty()

    def _echo(self, text: str, **style) -> None:
        click.echo(click.style(text, **style) if self.colour else text,
                   file=self.stream)

    def section(self, title: str) -> None:
        self._echo(f"\n{title}", fg=_ACCENT, bold=True)
        self._echo("─" * len(title), fg=_DIM)

    def success(self, message: str) -> None:
        self._echo(f"✓ {message}", fg="green")

    def error(self, message: str) -> None:
        click.echo(click.style(f"✗ {message}", fg="red") if self.colour
                   else f"✗ {message}", err=True)

    def warning(self, message: str) -> None:
        self._echo(f"⚠ {message}", fg="yellow")

    def info(self, message: str) -> None:
        self._echo(f"● {message}", fg="blue")

    def status(self, label: str, value: Any) -> None:
        self._echo(f"  {label}: {value}")

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]],
              max_width: int = 40) -> None:
        """Print a simple aligned table."""
        if not headers:
            return

        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = min(max(widths[i], len(str(cell))), max_width)

        def render(cells: Sequence[Any]) -> str:
            parts = []
            for i, cell in enumerate(cells):
                text = str(cell)
                if len(text) > widths[i]:
                    text = text[: widths[i] - 1] + "…"
                parts.append(text.ljust(widths[i]))
            return "  ".join(parts).rstrip()

        self._echo(render(headers), bold=True)
        self._echo("  ".join("─" * w for w in widths), fg=_DIM)
        for row in rows:
            self._echo(render(row))

    def prompt(self, text: str, count: int) -> int:
        """Ask for a 1-based selection. Callers must confirm a TTY first."""
        return click.prompt(f"{text} [1-{count}]",
                            type=click.IntRange(1, count))
```

- [ ] **Step 4: Point the CLI at the new UI**

In `src/printful_cli/printful_cli.py`, replace the ReplSkin import and accessor:

```python
from .ui import UI

_ui: Optional[UI] = None


def get_ui() -> UI:
    global _ui
    if _ui is None:
        _ui = UI()
    return _ui
```

Then replace every `get_skin()` call with `get_ui()`, every `skin.` with `ui.`, and delete the `print_banner`, `create_prompt_session`, `get_input`, `print_goodbye`, and `help` calls in `repl`, replacing the REPL's input loop with:

```python
    ui = get_ui()
    ui.section("printful")
    ui.info("Billable commands (orders confirm/cancel) still require --yes here.")
    while True:
        try:
            line = input("printful> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
```

and the help branch with:

```python
        if line in ("help", "?"):
            ui.section("Commands")
            for name, description in REPL_COMMANDS.items():
                ui.status(name, description)
            continue
```

- [ ] **Step 5: Update packaging**

In `pyproject.toml`:

```toml
[project.scripts]
printful-mcp = "printful_mcp.server:main"
printful = "printful_cli.printful_cli:main"
```

Remove `namespaces = true` and the `[tool.setuptools.package-data]` entry for `cli_anything.printful`, replacing it with:

```toml
[tool.setuptools.package-data]
"printful_cli" = ["skills/*.md"]
```

Update `testpaths`:

```toml
testpaths = ["src/printful_core/tests", "src/printful_cli/tests", "tests"]
```

- [ ] **Step 6: Reinstall and run the suite**

```bash
.venv/bin/python -m pip uninstall -y cli-anything-printful printful-mcp -q
.venv/bin/python -m pip install -e . -q
.venv/bin/printful --help
.venv/bin/python -m pytest -q
```

Expected: `printful --help` lists the command groups; the offline suite passes.

- [ ] **Step 7: Verify the live suite still passes**

```bash
set -a && . ./.env && set +a
export PRINTFUL_STORE_ID=1135966
PATH="$PWD/.venv/bin:$PATH" CLI_ANYTHING_FORCE_INSTALLED=1 \
    .venv/bin/python -m pytest -m live -q
```

Expected: 18 passed, 3 skipped. If `_resolve_cli` fails, update it in
`src/printful_cli/tests/test_full_e2e.py` to resolve `printful` rather than
`cli-anything-printful`, and rename the environment variable it reads to
`PRINTFUL_FORCE_INSTALLED`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: rename the CLI package to printful_cli

Drops the cli-anything namespace package and the 567-line vendored REPL skin,
which printed a cli-anything banner and an npx install hint for a framework
this project does not use. A local ui.py of about 120 lines replaces it. The
command is now 'printful'."
```

---

## Task 14: Move the CLI onto the core

**Files:**
- Delete: `src/printful_cli/utils/printful_backend.py`
- Modify: `src/printful_cli/core/*.py`, `src/printful_cli/printful_cli.py`
- Modify: `src/printful_cli/tests/test_core.py` (drop tests now covered by the core)

**Interfaces:**
- Consumes: every `printful_core` module
- Produces: a CLI with no HTTP code of its own

- [ ] **Step 1: Confirm the current suite is green before changing anything**

```bash
.venv/bin/python -m pytest -q
```

Expected: all pass. Record the count; it will drop as duplicated tests are removed.

- [ ] **Step 2: Replace one domain module and watch it pass**

Rewrite `src/printful_cli/core/catalog.py` to call the core:

```python
"""Catalog operations for the CLI."""
from __future__ import annotations

from typing import Any, Dict, Optional

from printful_core.endpoints import catalog as endpoints
from printful_core.format import summary
from printful_core.transport import SyncTransport


def list_products(transport: SyncTransport, limit: int = 20, offset: int = 0,
                  category_ids: Optional[str] = None,
                  colors: Optional[str] = None,
                  techniques: Optional[str] = None,
                  types: Optional[str] = None) -> Dict[str, Any]:
    response = transport.send(endpoints.list_products(
        limit, offset, category_ids, colors, techniques, types))
    return summary.products(response)


def get_product(transport: SyncTransport, product_id: int) -> Dict[str, Any]:
    return transport.send(endpoints.get_product(product_id))


def list_variants(transport: SyncTransport, product_id: int,
                  limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    return summary.variants(
        transport.send(endpoints.list_variants(product_id, limit, offset)))


def get_variant_prices(transport: SyncTransport, variant_id: int,
                       currency: Optional[str] = None) -> Dict[str, Any]:
    return transport.send(endpoints.get_variant_prices(variant_id, currency))


def get_availability(transport: SyncTransport, product_id: int,
                     techniques: Optional[str] = None) -> Dict[str, Any]:
    return transport.send(endpoints.get_availability(product_id, techniques))


def list_categories(transport: SyncTransport, limit: int = 20,
                    offset: int = 0) -> Dict[str, Any]:
    return transport.send(endpoints.list_categories(limit, offset))


def get_category(transport: SyncTransport, category_id: int) -> Dict[str, Any]:
    return transport.send(endpoints.get_category(category_id))


def get_size_guide(transport: SyncTransport, product_id: int,
                   unit: Optional[str] = None) -> Dict[str, Any]:
    return transport.send(endpoints.get_size_guide(product_id, unit))
```

- [ ] **Step 3: Run the catalog-related tests**

```bash
.venv/bin/python -m pytest src/printful_cli/tests -k catalog -v
```

Expected: tests referencing the removed `summarize_products` fail. Delete those tests — `src/printful_core/tests/test_format.py` now covers them — and keep any that assert CLI behavior.

- [ ] **Step 4: Rewrite `shipping.py`, which owns the pagination call**

```python
"""Shipping operations for the CLI."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from printful_core.endpoints import shipping as endpoints
from printful_core.format import summary
from printful_core.pagination import collect_pages
from printful_core.transport import SyncTransport


def list_countries(transport: SyncTransport) -> Dict[str, Any]:
    """Every page. A single request omits the US."""
    response = collect_pages(endpoints.list_countries(), transport.send)
    return summary.countries(response)


def calculate_rates(transport: SyncTransport, recipient: Dict[str, Any],
                    items: List[Dict[str, Any]],
                    currency: Optional[str] = None) -> Dict[str, Any]:
    response = transport.send(
        endpoints.calculate_rates(recipient, items, currency))
    return summary.rates(response)


def calculate_tax(transport: SyncTransport, country_code: str,
                  state_code: Optional[str] = None,
                  city: Optional[str] = None,
                  zip_code: Optional[str] = None) -> Dict[str, Any]:
    return transport.send(
        endpoints.calculate_tax(country_code, state_code, city, zip_code))
```

- [ ] **Step 5: Rewrite `orders.py`, which owns the polling loops**

```python
"""Order operations for the CLI.

confirm_order charges the account and cancel_order is destructive. Both are
gated behind --yes in the command layer, not here.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from printful_core.endpoints import orders as endpoints
from printful_core.errors import PrintfulError
from printful_core.format import summary
from printful_core.transport import SyncTransport


def list_orders(transport: SyncTransport, limit: int = 20, offset: int = 0,
                status: Optional[str] = None) -> Dict[str, Any]:
    return summary.orders(
        transport.send(endpoints.list_orders(limit, offset, status)))


def get_order(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    return transport.send(endpoints.get_order(order_id))


def create_order(transport: SyncTransport, recipient: Dict[str, Any],
                 items: List[Dict[str, Any]],
                 external_id: Optional[str] = None) -> Dict[str, Any]:
    return transport.send(
        endpoints.create_order(recipient, items, external_id))


def update_order(transport: SyncTransport, order_id: str,
                 changes: Dict[str, Any]) -> Dict[str, Any]:
    return transport.send(endpoints.update_order(order_id, changes))


def cancel_order(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    result = transport.send(endpoints.cancel_order(order_id))
    return result or {"order_id": order_id, "status": "cancelled"}


def confirm_order(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    """CHARGES THE ACCOUNT. The command layer requires --yes first."""
    return transport.send(endpoints.confirm_order(order_id))


def list_items(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    return transport.send(endpoints.list_items(order_id))


def list_shipments(transport: SyncTransport, order_id: str) -> Dict[str, Any]:
    return transport.send(endpoints.list_shipments(order_id))


def estimate_costs(transport: SyncTransport, recipient: Dict[str, Any],
                   items: List[Dict[str, Any]], poll: bool = True,
                   max_wait: float = 30.0,
                   interval: float = 2.0) -> Dict[str, Any]:
    """Create an estimation task and poll until it leaves 'pending'."""
    task = transport.send(endpoints.create_estimation_task(recipient, items))
    body = task.get("data", task) if isinstance(task, dict) else {}
    task_id = body.get("id")
    if not poll or not task_id:
        return task

    deadline = time.monotonic() + max_wait
    latest = task
    while time.monotonic() < deadline:
        latest = transport.send(endpoints.get_estimation_task(task_id))
        current = latest.get("data", latest) if isinstance(latest, dict) else {}
        status = current.get("status")
        if status == "completed":
            return latest
        if status == "failed":
            reasons = current.get("failure_reasons") or []
            raise PrintfulError(
                "Order estimation failed: "
                + ("; ".join(str(r) for r in reasons) or "no reason given"),
                detail=current)
        time.sleep(interval)

    raise PrintfulError(
        f"Order estimation task {task_id} still pending after {max_wait}s.",
        detail={"task_id": task_id, "last_response": latest})
```

- [ ] **Step 6: Rewrite the four remaining modules**

`mockups.py`, `files.py`, `stores.py`, and `sync.py` follow the shape of
`catalog.py` in Step 2: import the matching `printful_core.endpoints` module,
call `transport.send(endpoints.<operation>(...))`, and pass list responses
through `summary.<name>`. `mockups.py` additionally keeps its `wait_for_task`
polling loop, which changes only in that it calls
`transport.send(endpoints.get_task(task_id))` instead of the old backend.
`files.py` keeps `list_added(session_files)` unchanged: it reads the session
record, not the API, because Printful exposes no list-files endpoint.

- [ ] **Step 7: Swap the backend for the transport in the CLI entry point**

In `src/printful_cli/printful_cli.py`, replace the backend accessor:

```python
from printful_core.auth import Credentials
from printful_core.transport import SyncTransport

_transport: Optional[SyncTransport] = None


def get_transport(ctx) -> SyncTransport:
    """Build the transport lazily so --help and config need no token."""
    global _transport
    if _transport is None:
        credentials = Credentials.resolve(
            api_key=ctx.obj.get("api_key"),
            store_id=ctx.obj.get("store_id") or get_session().store_id,
        )
        _transport = SyncTransport(credentials)
    return _transport
```

Replace every `get_backend(ctx)` call with `get_transport(ctx)`. Update the error imports:

```python
from printful_core.errors import (
    PrintfulAuthError, PrintfulError, PrintfulRateLimitError,
)
from printful_core.auth import CONFIG_FILE, load_config, save_config
```

- [ ] **Step 8: Delete the superseded backend**

```bash
rm src/printful_cli/utils/printful_backend.py
grep -rn 'printful_backend' src/ || echo "no references remain"
```

Expected: `no references remain`

- [ ] **Step 9: Run the offline suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: all pass. Roughly 150 tests once the duplicated backend and summarizer tests are removed.

- [ ] **Step 10: Run the live suite**

```bash
set -a && . ./.env && set +a
export PRINTFUL_STORE_ID=1135966
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -m live -q
```

Expected: 18 passed, 3 skipped. This is the real gate: the CLI now reaches the
live API entirely through the core.

- [ ] **Step 11: Confirm `requests` is gone**

```bash
grep -rn 'import requests' src/ || echo "no direct requests usage"
```

Expected: `no direct requests usage`. Remove `"requests>=2.28.0"` from
`dependencies` in `pyproject.toml`, then reinstall:

```bash
.venv/bin/python -m pip install -e . -q
.venv/bin/python -m pytest -q
```

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: move the CLI onto printful_core

The CLI no longer builds URLs, sets headers, parses errors, or paginates. Every
operation goes through a core request builder and the shared transport, so the
MCP server can reuse the same definitions without a second implementation free
to drift from this one. Drops the requests dependency in favour of httpx."
```

---

## Verification

After Task 14, all of the following must hold:

```bash
# Offline suite passes with no credentials
.venv/bin/python -m pytest -q

# Live suite passes with credentials
set -a && . ./.env && set +a && export PRINTFUL_STORE_ID=1135966
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -m live -q

# Both entry points work
.venv/bin/printful --version
.venv/bin/python -c "
from printful_mcp.server import mcp
import asyncio
print('mcp tools:', len(asyncio.run(mcp.list_tools())))
"

# The upstream series is intact and carries no core references
git log --oneline upstream-base~3..upstream-base
git show upstream-base~2..upstream-base --stat | grep printful_core \
    && echo "FAIL: upstream commits reference the core" \
    || echo "OK: upstream commits are clean"
```

Expected: offline green, live green, `printful` reports its version, the MCP server registers 19 tools, and the upstream series contains no reference to `printful_core`.

## What Plan 2 picks up

The MCP server still uses `src/printful_mcp/client.py` and its own `tools/`
implementations. Plan 2 rebuilds it on the core and adds the fourteen tools that
close parity. `client.py` is deleted there, not here, so the upstream series
keeps working throughout this plan.
