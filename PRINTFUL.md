# PRINTFUL.md — Agent Harness SOP for the Printful API

Software-specific standard operating procedure for `cli-anything-printful`, built per
`HARNESS.md`. This document records the Phase 1 analysis and the Phase 2 architecture
decisions, including the two places this harness deliberately deviates from the
GUI-oriented parts of the harness spec.

## Phase 1: Analysis

### The "software" is a hosted REST API

Printful is SaaS. There is no source tree to clone, no executable to locate with
`shutil.which()`, no native project file format, and no undo/redo command pattern.
The harness spec's Phase 1 steps assume an open-source GUI app; they do not apply
literally here.

**Recorded deviation #1 — HTTP backend instead of a subprocess backend.**
`utils/printful_backend.py` is the backend module required by Phase 3, but it wraps
HTTPS calls to `api.printful.com` rather than a local binary. This follows the
existing precedent in this marketplace: `cli-anything-novita` and `cli-anything-exa`
are both API-service harnesses with the same shape.

This does **not** relax the harness's #1 rule ("Use the Real Software — Don't
Reimplement It"). The real software here *is* the Printful API, and every command
calls it live. Nothing about catalog data, pricing, shipping rates, or mockup
rendering is simulated locally.

**Recorded deviation #2 — no rendering gap.** Printful renders mockups server-side
and returns URLs. There is no local render path to translate filters into, so the
"Rendering Gap" and "Filter Translation" sections of `HARNESS.md` do not apply.
Output verification instead means validating API response structure and, for mockups,
confirming the returned URLs are reachable and serve real image bytes.

### Source inputs

| Input | Role |
|---|---|
| `src/printful_mcp/` (this repo) | Proven endpoint paths, auth model, v1/v2 error handling. The MCP server's 19 tools are the verified baseline. |
| `https://developers.printful.com/docs/` | v1 reference. Source of the auth/error/store-header semantics and of the endpoints v2 lacks (tax, product templates, sync). |
| `https://developers.printful.com/docs/v2-beta/` | v2 reference. Source of the catalog, order, shipping, file, and mockup surface. |

### Data model

There is no project file. The equivalent persistent state is:

- **Draft order under construction** — recipient, line items, shipping preference.
  Building an order is genuinely multi-step (find product → pick variant → check
  price → add item → set recipient → rate shipping → create draft → confirm), which
  is what justifies a stateful CLI and a REPL over a pile of one-shot curl calls.
- **Selected store** — for account-level tokens, the `X-PF-Store-Id` context.
- **File records** — file IDs returned by `files add`, needed later for mockups and
  order items.
- **Command history** — for `session history`.

### API versioning

v2 is primary. v1 is used only where v2 has no equivalent:

| Feature | Version | Path |
|---|---|---|
| Catalog, orders, shipping rates, countries, files, mockups, stores | v2 | `/v2/...` |
| Tax rate calculation | v1 | `/tax/rates` |
| Product templates | v1 | `/product-templates` |
| Sync products | v1 | `/store/products` |

Response and error shapes differ by version and the backend normalizes both:

- v2 success returns the body as-is; v1 success is unwrapped from `{"code", "result"}`.
- **Errors: the v2 docs are wrong.** They describe RFC 9457 problem details
  (`detail`/`title`), but the live v2 API returns the v1-style envelope for both
  4xx and 404:

  ```json
  {"data": "Product 99999999 does not exist or is inactive.",
   "error": {"reason": "NotFound", "message": "..."}}
  ```

  Verified against live 400 and 404 responses. A client that reads only
  `detail`/`title` reduces every v2 error to "Unknown error" and hides the cause.
  `_extract_error_message` tries all known shapes regardless of version.

  Note: `src/printful_mcp/client.py:141` in the parent repo has this bug.

## Phase 2: Architecture

### Command groups

```
catalog   products, product, variants, variant-price, availability,
          categories, category, size-guide
orders    list, get, create, update, cancel, confirm, estimate, items, shipments
ship      rates, countries, tax
mockup    create, status, styles, templates
files     add, get, list
store     list, stats, templates, use
sync      products, get
draft     show, recipient, add-item, remove-item, clear, submit
session   status, draft, history, clear
config    set, get, delete, path
test      connectivity check
repl      interactive mode (default when no subcommand is given)
```

### Safety model — this CLI spends real money

This is the defining constraint of the harness and it shapes the command design, not
just the tests.

| Command | Effect | Guard |
|---|---|---|
| `orders confirm` | **Submits for fulfillment. Charges the account.** | Requires `--yes`. Refuses with a clear message otherwise. |
| `orders cancel` | Deletes/cancels an order | Requires `--yes`. |
| `orders create` / `draft submit` | Creates a **draft** — not charged | None; drafts are safe and reversible. |
| `files add` | Uploads to the file library | None; cheap and non-destructive. |
| `mockup create` | Burns the account's 20,000 files/24h cap; hard rate limit | Warns on new-store limits; surfaces 429 verbatim. |

Rules:

- No command charges the account without an explicit `--yes` on that invocation.
  There is no persistent "always allow" setting, by design.
- `--dry-run` suppresses session writes (per the harness auto-save requirement) and
  additionally prints the request that *would* be sent for mutating commands.
- Rate limits are surfaced, never silently retried. The general limit is 120 req/60s;
  **mockup creation is far stricter — 10/60s for established stores and 2/60s for new
  stores, with a 60s lockout.** A CLI that auto-retried would walk an unsuspecting
  user into a lockout, so the backend raises and prints `Retry-After`.

### State model

Session file: `~/.cli-anything-printful/session.json`, overridable with `--session`.
Written through `_locked_save_json` (exclusive `fcntl` lock, per
`guides/session-locking.md`).

Auto-save fires via `@cli.result_callback()` after one-shot mutations, skipped in REPL
mode and under `--dry-run`.

Config file: `~/.config/cli-anything-printful/config.json`.
Credential precedence: `--api-key` flag → `PRINTFUL_API_KEY` env → config file.
Same for store ID (`--store-id` → `PRINTFUL_STORE_ID` → config).

### Output

Every command supports `--json`. Human mode uses `ReplSkin` tables and status blocks;
`--json` emits a single parseable object on stdout with no decoration.

### Known API limitations, surfaced rather than hidden

- **There is no "list files" endpoint** in either v1 or v2 — both expose only "add a
  file" and "get a file by ID". `files list` therefore reports the files *this CLI has
  added in the current session*, read from the session record, and says so in its
  output. It is not a server query.
- **Order cost estimation is asynchronous.** `orders estimate` creates a task and polls
  `GET /v2/order-estimation-tasks?id=...` until the status leaves `pending`.
- **`/v2/countries` is paginated** and defaults to 20 of 239 rows. `US` is not in the
  first page alphabetically, so a naive single-request client reports that Printful
  does not ship to the United States. `list_countries` fetches every page.
- **A catalog order item requires `placements`.** Printful rejects an order item with
  no artwork ("Property `placements` is required") — there is nothing to print.
  Shipping rates, however, *can* be quoted without artwork. The draft model tracks
  this asymmetry: `priceable()` is true without a design, `is_complete()` is not.
- **`/v2/shipping-rates` rejects an item without `source`** ("must be of type
  `string`, `null` provided"), so `calculate_rates` defaults it to `catalog`.
- **Shipping rate rows are keyed `shipping` and `shipping_method_name`**, not `id`
  and `name`. Reading `id`/`name` yields a table of nulls.
- **Account-level tokens must select a store.** Every store-scoped endpoint returns
  "This endpoint requires `store_id`!" until one is chosen. `store use` (no argument)
  presents an interactive picker; `store use <ID> --save` sets the default. In
  `--json` mode or a non-TTY the picker refuses and returns the store list instead
  of blocking on a prompt.
- **Mockup generation is asynchronous.** `mockup create` returns a task ID;
  `mockup status` polls it.
- Private tokens expire and cannot be refreshed; `test` reports an auth failure with
  that hint.

### Endpoint paths

Every path below is either used by the MCP server in this repo (proven working) or read
verbatim from the published v1/v2 references.

| Command | Method | Path | Version |
|---|---|---|---|
| `catalog products` | GET | `/catalog-products` | v2 |
| `catalog product` | GET | `/catalog-products/{id}` | v2 |
| `catalog variants` | GET | `/catalog-products/{id}/catalog-variants` | v2 |
| `catalog variant-price` | GET | `/catalog-variants/{id}/prices` | v2 |
| `catalog availability` | GET | `/catalog-products/{id}/availability` | v2 |
| `catalog categories` | GET | `/catalog-categories` | v2 |
| `catalog category` | GET | `/catalog-categories/{id}` | v2 |
| `catalog size-guide` | GET | `/catalog-products/{id}/sizes` | v2 |
| `orders list` | GET | `/orders` | v2 |
| `orders get` | GET | `/orders/{id}` | v2 |
| `orders create` | POST | `/orders` | v2 |
| `orders update` | PATCH | `/orders/{id}` | v2 |
| `orders cancel` | DELETE | `/orders/{id}` | v2 |
| `orders confirm` | POST | `/orders/{id}/confirmation` | v2 |
| `orders estimate` (create) | POST | `/order-estimation-tasks` | v2 |
| `orders estimate` (poll) | GET | `/order-estimation-tasks?id={id}` | v2 |
| `orders items` | GET | `/orders/{id}/order-items` | v2 |
| `orders shipments` | GET | `/orders/{id}/shipments` | v2 |
| `ship rates` | POST | `/shipping-rates` | v2 |
| `ship countries` | GET | `/countries` | v2 |
| `ship tax` | POST | `/tax/rates` | v1 |
| `mockup create` | POST | `/mockup-tasks` | v2 |
| `mockup status` | GET | `/mockup-tasks` | v2 |
| `mockup styles` | GET | `/catalog-products/{id}/mockup-styles` | v2 |
| `mockup templates` | GET | `/catalog-products/{id}/mockup-templates` | v2 |
| `files add` | POST | `/files` | v2 |
| `files get` | GET | `/files/{id}` | v2 |
| `store list` | GET | `/stores` | v2 |
| `store stats` | GET | `/stores/{id}/statistics` | v2 |
| `store templates` | GET | `/product-templates` | v1 |
| `sync products` | GET | `/store/products` | v1 |
| `sync get` | GET | `/store/products/{id}` | v1 |

## Testing strategy

The harness requires E2E tests against the real backend with no graceful degradation.
For a billable API that needs a split, stated here and in `tests/TEST.md`:

- **Read-only endpoints are tested live** against the real API with a real key:
  countries, catalog products/variants/prices/categories/size guides, stores, orders
  list. These are free and idempotent.
- **Draft order creation is tested live.** Drafts are not charged.
- **`orders confirm` and `orders cancel` are never called against the live API in
  tests.** They are covered by unit tests with a mocked transport that assert the
  `--yes` guard, the request shape, and the refusal path. Confirming a real order in a
  test run would charge the user.
- **Mockup creation is not exercised in the default E2E run.** The 2/60s new-store
  limit and the 20,000 file/24h account cap make it both flaky and costly. It is
  marked and opt-in via `PRINTFUL_E2E_MOCKUPS=1`.

This is a deliberate, documented coverage gap, not an oversight.
