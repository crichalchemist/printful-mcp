# Printful: shared core, two surfaces

**Date:** 2026-09-16
**Status:** Approved, pending implementation plan
**Repository:** `crichalchemist/printful-mcp` (fork of `Purple-Horizons/printful-mcp`)
**Target branch:** `dev`

## Problem

This repository is the first search result for "Printful MCP." A stranger who
finds it today gets a server that does not start, and a README that describes
features the code does not have.

Five defects, all confirmed against the live Printful API:

| Defect | Effect |
|---|---|
| `mcp>=0.9.0` floats into `mcp` 2.x, which renamed `FastMCP` to `MCPServer` | The server raises `ModuleNotFoundError` at import. A fresh `pip install -e .` produces nothing that runs. |
| v2 errors read as RFC 9457 (`detail`/`title`) | The live API returns `{"data": ..., "error": {"message": ...}}`. Every v2 error surfaced as `"Unknown error"`, hiding its own cause. |
| `create_order` sends no `order_items`, and no tool adds them | An order created through the MCP can never be filled. The README's headline workflow is a dead end. |
| `/v2/countries` paginates at 20 of 239 rows | `US` falls outside the first page. The tool reports that Printful does not ship to the United States. |
| README claims "full v2 coverage," "robust error handling," "rate limit management," "17 tools" | None hold. 19 tools are registered, covering roughly half the v2 surface, with no retry logic. |

A second problem drives the architecture. The repository now carries two
surfaces — the MCP server and a CLI — that speak to the same API through two
separately written HTTP stacks. The CLI's stack was verified against the live
API and the MCP's was not, which is exactly why the two disagree. Maintaining
one operation twice invites the two implementations to drift, and each drift is
a defect of the kind listed above.

## Goals

1. A stranger who installs this repository gets a working MCP server and a
   working CLI, and a README that describes only what the code does.
2. The MCP server reaches parity with the CLI: roughly 33 operations spanning
   the full order lifecycle, so the coverage claims become true by construction.
3. Endpoint paths, payload shapes, and error parsing live in one tested place.
4. Three fixes stay small and isolated enough to contribute upstream.

## Non-goals

- Rewriting the MCP server against the `mcp` 2.x `MCPServer` API. The pin
  restores service today; migration is a separate decision.
- Retry or backoff on rate limits. Surfacing `Retry-After` is deliberate: a CLI
  that silently retried would walk a user into Printful's 60-second mockup
  lockout.
- Webhooks and warehouse products. Both need infrastructure the user must run
  separately, and neither serves the store and product development workflow this
  targets.

## Architecture

Three packages under `src/`:

```
src/
    printful_core/    request specs, transport, errors, formatters
    printful_mcp/     MCP server
    printful_cli/     command-line interface
```

### The core performs no I/O

Each operation is a pure function returning a frozen `Request`:

```python
def list_products(limit=20, offset=0, **filters) -> Request:
    return Request("GET", "/catalog-products", params={"limit": limit, ...})
```

Both adapters build the same `Request` and hand it to their own transport. The
shared layer never touches the network, so asynchronous and synchronous callers
share it without accommodation.

```
printful_core/
    request.py       frozen Request(method, path, version, params, json)
    auth.py          credential and store resolution, header construction
    errors.py        exception types, normalize_error(body, status)
    transport.py     SyncTransport and AsyncTransport (httpx ships both)
    pagination.py    paginate(build_request, execute)
    endpoints/       catalog, orders, shipping, mockups, files, stores, sync
    format/          markdown.py (from the MCP), summary.py (from the CLI)
```

Four things become single-source, and every one of them caused a defect above:

- **Error normalization.** One function reads every envelope Printful returns.
- **Pagination.** `paginate()` walks pages generically, so the countries defect
  cannot recur per endpoint.
- **Headers.** `X-PF-Store-Id` is applied in one place.
- **Payload shapes.** `placements`, `source` defaulting, and rate keys are
  defined once.

Validation happens in the endpoint function, before any request exists. Asking
for a mockup with no variants raises immediately rather than after a round trip.

Transport uses `httpx` for both surfaces. It ships `Client` and `AsyncClient`
with matching APIs, so one module serves both and the `requests` dependency
disappears.

### The adapters stay thin

**MCP.** `models/inputs.py` remains and grows to roughly 33 Pydantic models,
because Pydantic supplies the JSON Schema that makes tools discoverable. Each
tool validates its input, builds a `Request`, awaits the asynchronous transport,
and formats the result.

**CLI.** Click options build a `Request`, the synchronous transport executes it,
and the formatter renders a table or JSON.

**Session state stays in the CLI.** The draft-order accumulator is a shell
concept. MCP tools are stateless, so `printful_create_order` accepts items
inline through `items_json`.

### The parity gap

The MCP registers 19 tools today. Fourteen operations close the gap:

| Group | New tools |
|---|---|
| orders | `update`, `cancel`, `items`, `shipments`, `estimate_costs` |
| catalog | `list_categories`, `get_category`, `get_size_guide` |
| mockup | `list_styles`, `list_templates` |
| shipping | `calculate_tax` |
| store | `list_templates` |
| files | *(none — `files list` is session-local and stays CLI-only)* |

Plus `create_order` gaining `items_json`, which ships as upstream commit 3.
That totals 33 MCP tools against 33 CLI commands.

### Dropping the cli-anything packaging

The CLI moves from `cli_anything/printful` to `printful_cli`, which removes the
PEP 420 namespace package and its `find_namespace_packages` configuration. The
command becomes `printful`.

This drops three things:

- `utils/repl_skin.py`, 567 vendored lines that print a `cli-anything` banner and
  an `npx skills add HKUDS/CLI-Anything` hint. A local `ui.py` of roughly 120
  lines replaces it. The REPL itself stays; it earns its place in draft-order work.
- `PRINTFUL.md`, whose harness framing no longer applies. Its API findings move
  to `docs/`.
- The `cli-anything-printful` distribution name.

The cost is losing the cli-anything shared namespace and its `npx skills add`
discovery path. This repository publishes a Printful tool rather than a harness
collection, so the trade favors a clean package.

## Commit sequencing

The restructure rewrites `src/printful_mcp/tools/`, which would make any later
upstream pull request unmergeable. Sequencing solves this; architecture cannot.

```
commit 1   fix: pin mcp<2 — server fails to import against 2.x    [pyproject.toml]
commit 2   fix: read the v2 error envelope the live API returns    [client.py]
commit 3   feat: accept order items when creating an order         [inputs.py, orders.py]
tag        upstream-base
commit 4+  everything else (fork only)
```

The upstream pull request cherry-picks commits 1 through 3 onto a branch cut
from `upstream/main`. It never sees the core.

**One hazard exists today.** The working tree holds the `mcp<2` pin and the
fork-only packaging changes in the same `pyproject.toml`. Splitting them is the
first task; committing as-is strands the pin.

Commit 3 is unwritten and is the most valuable contribution of the three.

### Contribution quality

These commits are read by the original author and by the agent that maintains
that repository, so each one teaches rather than merely asserts:

- The message states the observed behavior, the expected behavior, and the
  evidence. "Verified against a live 404: the API returns `error.message`, not
  `detail`."
- Every claim names its reproduction. Endpoint, status code, and response body.
- The pull request body reproduces each defect from a clean checkout and shows
  the live response that proves it.
- No fix arrives without a test that fails beforehand.

## The cull

**Delete:**

| File | Reason |
|---|---|
| `test_server.py`, `test_comprehensive.py`, `test_complete.py` | Not pytest modules; collecting them produces 14 failures. They call the live API. `test_complete.py` hardcodes store `14690720`, which belongs to the original author. All three claim 17 tools. |
| `run-tests.sh` | An interactive `read -p` menu that hangs every non-interactive caller. |
| `examples.py` | 202 lines of docstrings. Running it prints "see comments above." |
| `TESTING.md` | Documents the three deleted scripts. |
| `src/printful_mcp/client.py` | Superseded by `printful_core`. |
| CLI `utils/printful_backend.py` | Superseded by `printful_core`. |
| CLI `utils/repl_skin.py` | Vendored cli-anything branding. |
| `PRINTFUL.md` | Harness framing; findings move to `docs/`. |

**Keep:** `test-with-inspector.sh`, `cursor-mcp-config.json`,
`API_TOKEN_SETUP.md`, `API_SCOPES_REFERENCE.md`, and `LICENSE` unchanged.

**Rewrite:** `README.md` and `QUICKSTART.md`.

**Ignore:** add `.serena/` to `.gitignore`.

No deletion reaches the upstream pull request.

## Testing

The 122 existing tests are the only automated coverage this repository has ever
had, and they encode five findings that cost live API calls to discover. They
move rather than get rewritten.

| Current | Destination |
|---|---|
| `DraftOrder`, CLI guards (~42) | `printful_cli/tests/`, unchanged |
| Headers, responses, errors (~24) | `printful_core/tests/test_transport.py`, `test_errors.py` |
| Payload shapes | Pure `Request` assertions; the fake transport disappears |
| Summarizers | `printful_core/tests/test_format.py` |

New coverage:

- **One spec test per endpoint** (~33): method, path, version, params, body.
- **MCP adapter tests**, the first the server has ever had: each tool registers,
  validates its input, and maps to the expected `Request`.
- **Live suite** keeps its `live` marker and extends to MCP tools.

Gates:

- `pytest` runs offline and must pass with no credentials.
- `pytest -m live` requires `PRINTFUL_API_KEY` and fails loudly without it.

## Distribution

Modeled on `arscontexta`, which is simultaneously a plugin and the marketplace
that serves it.

```
.claude-plugin/
    plugin.json          name, version, description, author, license, keywords
    marketplace.json     source "./" — the repository serves itself
.mcp.json                the server declaration the plugin installs
skills/
    printful-mcp/        SKILL.md + skill.json
    printful-cli/        SKILL.md + skill.json
.codex-plugin/
    plugin.json          interface block for Codex
    INSTALL.md
.agents/AGENTS.md        symlink to .claude/CLAUDE.md
.gemini/GEMINI.md        symlink to .claude/CLAUDE.md
scripts/bump-version.sh  synchronize the version across every manifest
```

A self-hosting marketplace makes installation one command:

```
/plugin marketplace add crichalchemist/printful-mcp
```

### Zero-install server declaration

`.mcp.json` runs the server through `uvx`, so no user ever needs `pip install`:

```json
{
  "mcpServers": {
    "printful": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/crichalchemist/printful-mcp@dev",
               "printful-mcp"],
      "env": { "PRINTFUL_API_KEY": "${PRINTFUL_API_KEY}" }
    }
  }
}
```

Verified: `uvx --from . printful-mcp` starts the server and speaks JSON-RPC over
stdio.

### Version synchronization

The version appears in `pyproject.toml`, `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, and each
`skill.json`. `scripts/bump-version.sh` writes all of them, and CI fails when
they disagree.

## Continuous integration

`.github/workflows/ci.yml`, on push and pull request:

| Job | Purpose |
|---|---|
| **test** | Python 3.10, 3.11, 3.12. Install, `ruff check`, `ruff format --check`, `pytest`. Offline only, so it needs no secrets and passes on a fork. |
| **server-boots** | Import the server and assert it registers the expected tool count. This job exists because the repository shipped broken for the entire life of `mcp` 2.x, and it catches that class of break on the day it appears. |
| **manifests** | Validate every JSON manifest, confirm the versions agree, and confirm each referenced path exists. |
| **upstream-drift** *(weekly, non-blocking)* | Install the newest `mcp` without the pin and report whether the server still imports. Announces when 2.x migration becomes worthwhile instead of discovering it through a user's bug report. |
| **live** *(weekly, gated on a secret)* | Run `pytest -m live` against the real API. Printful's v2 beta drifts; all five defects were shape mismatches this job would have caught. Skipped automatically on forks. |

`.pre-commit-config.yaml` runs `ruff` and a manifest-version check locally.

## Implementation phases

Each phase leaves the repository working and its tests green.

1. **Split the working tree.** Separate the `mcp<2` pin from the fork-only
   packaging, land commits 1 and 2, write commit 3 with a failing test first,
   tag `upstream-base`.
2. **Extract the core.** Move transport, errors, auth, and pagination out of the
   CLI backend into `printful_core`; migrate the tests that cover them.
3. **Build the endpoint layer.** One pure function per operation, one spec test
   each. The CLI switches to it and its live suite must stay green.
4. **Rebuild the MCP on the core.** Port the 19 existing tools, then add the 14
   that close parity. First automated tests for the server.
5. **Cull and rewrite the documentation.**
6. **Add distribution and CI.**

## Risks

| Risk | Mitigation |
|---|---|
| The MCP server has no tests, so the restructure changes unverified code. | Extract the core from the CLI side, which carries 122 tests. The core arrives tested; only the thin adapter is new. |
| Parity multiplies the surface from 19 tools to ~33. | Each operation is one pure function plus two bindings. The spec tests are pure and cost nothing to run. |
| Printful's v2 beta may drift again. | The weekly live job. |
| The pin holds the server on `mcp` 1.x indefinitely. | The weekly drift job reports when migration is viable. |

## Attribution

This is a fork. `LICENSE` stays unchanged, and the README preserves the upstream
citation form: the Resources and Links table naming Purple Horizons and Gianni
D'Alerta, and the license block crediting Purple Horizons LLC. The README states
plainly what the fork changes and links to the upstream repository.

## Decisions taken

- **The command is `printful`.** It reads better than `printful-cli` and no PyPI
  package currently claims the name. Reversible before release.
- **The upstream pull request carries the three code fixes only.** Rewriting
  another maintainer's README in a pull request presumes on their voice, and the
  claim corrections are entangled with parity work that stays in the fork. The
  pull request body reports the documentation inaccuracies as findings and
  leaves the wording to the author.
