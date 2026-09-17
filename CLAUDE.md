# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
.venv/bin/pip install -e ".[dev]"  # install with pytest + ruff
.venv/bin/python -m printful_mcp   # MCP server, stdio transport (default)
.venv/bin/python -m printful_mcp --transport http --port 8000   # streamable-http on /mcp
.venv/bin/printful-mcp             # same server, via the installed console script
.venv/bin/printful --help          # the CLI surface (src/printful_cli/)
npx @modelcontextprotocol/inspector .venv/bin/python -m printful_mcp   # interactive tool UI
```

**Every command above spells out `.venv/bin/`,** for the same reason the test commands below
do: the install puts nothing on your `PATH`, and `source .venv/bin/activate` does not persist
between an agent's tool calls. A bare `python` under an MCP client is the single most common
reason a working install does not start.

`PRINTFUL_API_KEY` must be set (via `.env` or environment) or `__main__.main()` exits 1
before the server starts.

### Tests

```bash
.venv/bin/python -m pytest              # offline suite — no network, no credentials
.venv/bin/python -m pytest -m live      # live API suite
.venv/bin/python -m pytest -m ""        # everything
.venv/bin/python -m pytest src/printful_mcp/tests/test_server.py -v   # one file
```

**Use `.venv/bin/python -m pytest`, not a bare `pytest`.** A bare invocation runs whichever
interpreter is first on `PATH`, not this project's venv, so what breaks depends on what that
interpreter happens to have installed — the symptoms are machine-specific and have changed more
than once. Today they are the `TestCLISubprocess` cases in
`src/printful_cli/tests/test_full_e2e.py`, where `_resolve_cli` (`:60`) falls back to
`[sys.executable, "-m", module]` and that interpreter cannot import `printful_cli`, plus
`TestCLIGuards.test_confirm_refusal_mentions_charging` and
`test_cancel_without_yes_exits_nonzero` in `src/printful_cli/tests/test_core.py`, which fail on a
different `click` with `I/O operation on closed file`.

**Those last two are the order-confirmation charge guards**, so a bare invocation shows the
safety tests for a billable operation red and invites the conclusion that the guard is broken.
It is not; the interpreter is wrong. Note also that `source .venv/bin/activate` does not persist
between an agent's tool calls, so the explicit path is the correct form regardless.

**Do not pass a directory path to run "the suite."** An explicit path argument overrides
`testpaths`, so `pytest tests/` collects three cases out of the whole suite, reports
`3 passed`, and runs none of the MCP adapter tests. (A path to one file, as in the line above,
is fine — that's running one file on purpose, not standing in for the suite.)

- **The offline suite must pass with `PRINTFUL_API_KEY` and `PRINTFUL_STORE_ID` unset.** If a
  test needs credentials, it is a live test and belongs behind the marker.
- **Unsetting the variable does not prove that.** `server.py` calls `load_dotenv()` at import,
  so a `.env` in the repo root puts `PRINTFUL_API_KEY` back into `os.environ` the moment any
  test imports the server — `env -u PRINTFUL_API_KEY pytest` then passes for the wrong reason.
  To check the constraint honestly, take `.env` out of the picture for the run:

  ```bash
  mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
  ```
- **Live tests are not softened.** `addopts = "-m 'not live'"` keeps them out of the default
  selection so a fresh clone gets a clean result. Selected without credentials they fail loudly
  rather than skip.
- **The live suite needs `PRINTFUL_STORE_ID` exported, not just `PRINTFUL_API_KEY`.** The token
  is account-level; the API rejects store-scoped calls without the `X-PF-Store-Id` header, and
  the draft-order tests then fail in a way that reads exactly like an order-path regression.
- **`printful_confirm_order` must never run against the live API.** It submits an order for
  fulfillment and charges a real account. It is asserted only against fake transports.
- **Mockup creation is opt-in behind `PRINTFUL_E2E_MOCKUPS=1`.** Printful rate-limits new stores
  to 2 requests per 60 seconds with a 60-second lockout. Do not set the flag to make more tests
  run.

### Lint

```bash
.venv/bin/ruff check src/ tests/ scripts/            # lint
.venv/bin/ruff format --check src/ tests/ scripts/   # formatting, non-mutating
.venv/bin/ruff format src/ tests/ scripts/           # formatting, applied
```

Both gates must be clean before a commit. The selected rules and the 100-column line length
live in `pyproject.toml` under `[tool.ruff]` — change them there, not with per-file ignores.

**That scope is the test boundary, and both narrowing and widening it have already caused
bugs.** `testpaths` runs `src/` and `tests/`, and `scripts/` holds `check_manifests.py`;
`.github/workflows/ci.yml` and `.pre-commit-config.yaml` use exactly this scope. Linting only
`src/` is how `tests/test_create_order.py` sat inside the default suite with two ruff findings
and nothing checking it. Widening to `.` is not the fix: ruff formats Python inside Markdown
fences, and the plan documents under `docs/superpowers/` are an execution record that no gate
may rewrite.

**CI runs these for you; the pre-commit hook does not install itself.**
`.github/workflows/ci.yml` runs both ruff gates and the offline suite on Python 3.10, 3.11 and
3.12 on every push and pull request, plus a parity job, a manifest job, and two scheduled jobs.
`.pre-commit-config.yaml` is in the repository, but `.git/hooks/` is never version-controlled
and `pre-commit` is not in the `[dev]` extra, so a fresh clone has no hook until you add one:

```bash
.venv/bin/pip install pre-commit && .venv/bin/pre-commit install
```

## Architecture

Two user-facing surfaces sit on one shared core:

```
src/printful_core/    what a Printful call IS          (no I/O except transport.py)
src/printful_mcp/     MCP server, async, returns str
src/printful_cli/     Click CLI, sync, prints tables
```

The core is the reason this repository exists. Before it, the two surfaces each carried their
own HTTP client, their own error parsing and their own pagination, and they drifted — the same
bug had to be fixed twice and usually was not.

### `printful_core` — request specs, not requests

| Module | Responsibility |
|---|---|
| `request.py` | `Request`: a frozen description of an un-sent call |
| `endpoints/*.py` | pure functions returning a `Request`. **No I/O.** |
| `transport.py` | `SyncTransport` / `AsyncTransport`. The only module that touches the network. |
| `errors.py` | `PrintfulError` and envelope normalization for both API versions |
| `auth.py` | `Credentials.resolve()` — explicit argument, then env var, then config file |
| `pagination.py` | page arithmetic as pure functions; two thin drivers that loop |
| `polling.py` | poll an async task until it leaves `pending` |
| `format/markdown.py` | renderers the MCP tools return |
| `format/summary.py` | flattened rows the CLI tabulates |

```python
Request(method, path, version="v2", params={}, json=None)
```

`__post_init__` drops `None` params — so builders pass optional filters straight through
without a three-line dance — and shallow-copies `json`, because a frozen `Request` aliasing
the caller's dict is not frozen in the way callers read it.

**An endpoint builder never sends anything.** That is what makes the arithmetic testable
without a network and shareable between a sync and an async caller. Keep it that way: if you
find yourself wanting `await` in `endpoints/`, the logic belongs in `pagination.py` or
`polling.py` as a pure function with a driver.

### Adding an MCP tool means touching three files, in this order

1. **`models/inputs.py`** — one Pydantic `BaseModel` per tool holding every parameter.
2. **`tools/<domain>.py`** — `async def name(transport: AsyncTransport, params: XInput) -> str`,
   which builds a `Request` from `printful_core.endpoints`, sends it, and formats the result.
3. **`server.py`** — an `@mcp.tool(...)`-decorated delegate that does nothing but
   `return await <domain>.name(get_transport(), params)`.

`server.py` holds no business logic; it is the MCP surface and nothing else.

**The transport is a parameter, not a module global.** Tools take it first so every one of them
is testable against `src/printful_mcp/tests/conftest.py`'s `FakeTransport` with no patching.
Only `server.py` calls `get_transport()`.

### Invariants a new tool must preserve

- **Return `str`, never a dict.**
- **Every input model carries `format: Literal["markdown", "json"]`,** and the body branches on
  it: `json.dumps(data, indent=2)` for json, a `printful_core.format.markdown` renderer
  otherwise.
- **Errors are returned, not raised.** The tail of every tool body is
  `except PrintfulError as e: return f"Error: {e.message}"`, preceded by
  `except ValueError as e: return f"Error: {e}"` wherever the core validates input. An MCP
  client must see a readable string, never a traceback.
- **`@mcp.tool` always sets the full `annotations` dict** — `title`, `readOnlyHint`,
  `destructiveHint`, `idempotentHint`, `openWorldHint`. A client reads `destructiveHint` to
  decide whether to prompt a human, so on `printful_confirm_order` and `printful_cancel_order`
  it is a safety field, not documentation.
- **Complex parameters are deliberately flattened to strings**, not nested models: `items_json`
  takes a JSON array as text, and IDs come in comma-separated (`variant_ids`, `category_ids`,
  `techniques`). This is not laziness — nested and typed params break over HTTP-to-stdio bridges
  like mcporter. See the mcporter section of `.cursor/skills/printful-mcp/SKILL.md`.

### Tool parity is enforced, not documented

**32 tools are registered**, one per request builder the core defines.
`src/printful_mcp/tests/test_server.py` asserts the mapping in both directions by set
difference, so a builder with no tool and a tool calling a builder that does not exist each
fail by name. **The count is a consequence of that mapping, not a target.** If it changes,
read the failure — do not edit the number here or there to agree.

This exists because the number was wrong everywhere it was written down: the spec's prose said
fourteen new operations, its own table said twelve, and the code said thirteen.

### API versioning

`Request.version` selects the base URL, and `transport._normalize` unwraps the response:

- **v2 is the default** (`https://api.printful.com/v2`) and is returned as-is.
- **v1** is unwrapped from `{"code": ..., "result": ...}` down to `result`, and **the shape of
  `result` varies by endpoint** — `/store/products` gives a bare list, `/product-templates`
  gives `{"items": [...], "paging": {...}}`. A renderer for a v1 endpoint must handle what that
  endpoint actually returns; a v2-shaped `data`/`paging` read silently renders an empty page.
- **v1 is used only where v2 has no equivalent** — sync products, product templates, tax rates.
- **Error shapes do not differ by version, whatever the v2 documentation says.** The docs
  describe RFC 9457 problem details, but the live API returns the v1-style envelope —
  `{"data": "<message>", "error": {"reason": ..., "message": ...}}` — for 4xx and for 404 as
  well. So `errors.extract_message` tries `error.message` **first**, then `detail`, `title`,
  `data`, `result`, `message`, for both versions: the undocumented shape wins because it is
  the one that actually arrives, and reading only `detail`/`title` reduces every real error to
  "Unknown error". All of them become a `PrintfulError`.
- **429 raises immediately with no retry.** This is deliberate and is a spec non-goal: a silent
  retry walks a user into Printful's 60-second mockup lockout. The client reads `Retry-After`
  into the error and gives up. Do not add backoff.

### Credentials and store ID

`Credentials.resolve()` takes an explicit argument, then `PRINTFUL_API_KEY`, then the config
file. `PRINTFUL_STORE_ID` is optional and, when set, is sent as `X-PF-Store-Id` on every
request; it is needed for account-level (multi-store) tokens. Separately, `store_id` is a
*tool parameter* on `printful_get_store_stats` — the only tool that takes one.

**Never echo, print, or commit the API key.** The CLI's `config get` masks it.

### Transport lifecycle

`src/printful_mcp/transport.py` holds a lazily-initialized module global (`get_transport()`)
registered with `atexit`. **Do not reintroduce an MCPServer lifespan handler** for transport
setup or teardown — one was tried, it failed, and this design is what replaced it.

### The SDK pin has two bounds, and both are load-bearing

`mcp>=2,<3`. The server imports `MCPServer` from `mcp.server.mcpserver`; that module does not
exist in mcp 1.x, which called the class `FastMCP`. A 1.x install fails at import.

**The upper bound guards a subtler break.** HTTP host and port are `run()` keywords —
`mcp.run(transport="streamable-http", host=..., port=...)`. mcp 1.x instead carried them on
`mcp.settings`, and 2.x's `Settings` has no such fields, so the old form raises `ValueError`.
That break is reachable **only** through `--transport http` or `--transport sse`: the module
imports clean, the server boots clean, and a boot check sees nothing. This is why
`src/printful_mcp/tests/test_entrypoint.py` asserts the kwargs `__main__.py` hands `run()`
rather than merely that it does not raise, and why the `upstream-drift` CI job builds
`streamable_http_app()` instead of stopping at an import.

**Read annotation fields by their wire names.** `ToolAnnotations` spells them
`destructive_hint` in Python and aliases to `destructiveHint` on the wire. Assert against
`annotations.model_dump(by_alias=True)`; an attribute read pins the SDK's internal naming,
which changed between 1.x and 2.x while the wire contract did not.

## Known inconsistencies

Match the dominant pattern in new code; leave these as they are unless the task is to fix them.

- `tools/sync.py` defines `ListSyncProductsInput` / `GetSyncProductInput` locally instead of in
  `models/inputs.py`, and `server.py` imports them from the tools module.
- `printful_list_countries` is the only tool with no input model — it takes no arguments at all.
- `CreateMockupTaskInput.format` means *image* format (`"jpg"` / `"png"`), not output format.
  It is the one exception to the `format: Literal["markdown", "json"]` invariant. Do not
  "fix" it by renaming.

## Related files

- `AGENTS.md` — the cross-tool entry point other agents look for. A pointer to this file, not a
  copy of it; keep it that way, because two files with the same content drift.
- `.cursor/skills/printful-mcp/SKILL.md` — guidance for the *consuming* assistant (tool
  reference, workflows, troubleshooting), not for working on this codebase. Its tool reference
  is kept one-to-one with the registered surface; if you add or rename a tool, add or rename the
  entry in the same commit.
- `src/printful_cli/skills/SKILL.md` — the same thing for the CLI surface: command groups,
  agent rules, and the guards on billable operations.
- `API_TOKEN_SETUP.md` / `API_SCOPES_REFERENCE.md` — which token scopes each tool group needs.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` — the design and execution record for
  the core extraction and the MCP rebuild.
