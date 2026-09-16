# TEST.md — cli-anything-printful

Part 1 (plan) was written before any test code, per `HARNESS.md` Phase 4.
Part 2 (results) is appended after execution, per Phase 6.

---

# Part 1: Test Plan

## The constraint that shapes this plan

The backend for this harness is a **live, billable, rate-limited third-party API**
that requires the operator's own private credentials. That differs from a harness
wrapping a local binary in three ways that the test strategy has to respect:

1. **Some operations cost real money.** `orders confirm` submits an order to
   production and charges the account. A test suite that called it would bill the
   user every run.
2. **Some operations are destructive.** `orders cancel` cannot be undone.
3. **Mockup generation is severely rate limited** — 10 req/60s for established
   stores, 2 req/60s for new stores, 60-second lockout on exceeding it, and a
   20,000-file/24h account cap. Any suite that exercised it would be flaky and
   would consume a resource the user pays for.

`HARNESS.md` requires E2E tests that invoke the real backend with no graceful
degradation. That rule is honored for everything that is free and safe, and
deliberately **not** applied to the three categories above. The split is stated
here rather than discovered later.

## Test Inventory Plan

| File | Type | Planned count | Network |
|---|---|---|---|
| `test_core.py` | Unit — synthetic data + mocked transport | ~40 | None |
| `test_full_e2e.py` | E2E — live API + CLI subprocess | ~20 | Required |

## Unit Test Plan (`test_core.py`)

No network. A `FakeResponse`/`FakeSession` pair is injected into `PrintfulBackend`
so request construction and response normalization can be asserted exactly.

### `core/session.py` — `DraftOrder`
- `set_recipient` stores known fields; rejects unknown fields loudly (`ValueError`).
- `add_item` builds a catalog-source item; rejects `quantity < 1`.
- `add_item` with `image_url` nests a placement with the right technique/placement.
- `remove_item` pops by index; raises on out-of-range and on an empty draft, with
  the valid index range named in the message.
- `missing_fields` reports each absent required recipient field.
- `missing_fields` requires `state_code` for US, CA, AU and not for other countries.
- `is_complete` flips only when recipient and items are both satisfied.
- `to_api_payload` raises while incomplete; emits `recipient` + `order_items` when
  complete; includes `external_id` and `shipping` only when set.
- `summary` counts items and total quantity correctly.

### `core/session.py` — `PrintfulSession`
- Round-trips draft, store, files, and history through save/load.
- `record_file` appends a record and marks the session modified.
- `save_history` appends and truncates at `MAX_HISTORY` (50).
- `clear` empties draft, files, and history.
- Corrupt session JSON loads as an empty session rather than crashing.
- `_locked_save_json` creates parent directories.

### `utils/printful_backend.py`
- Credential precedence: explicit argument beats env var beats config file.
- Missing credentials raise `PrintfulAuthError` with setup instructions.
- `X-PF-Store-Id` is sent when a store ID is set and omitted when it is not.
- `Authorization: Bearer` is always sent.
- v2 success returns the body unchanged.
- v1 success unwraps `{"code", "result"}` down to `result`.
- v2 error uses RFC 9457 `detail`, falling back to `title`.
- v1 error uses `error.message`.
- 401 raises `PrintfulAuthError` mentioning token expiry.
- 403 raises `PrintfulAuthError` mentioning scopes.
- 429 and 419 raise `PrintfulRateLimitError` carrying `Retry-After`.
- 204 / empty body returns `{}` rather than raising.
- `None`-valued query params are dropped before the request is sent.
- Timeouts raise `PrintfulError` naming the URL.

### `core/orders.py`
- `update_order` rejects an empty payload.
- `confirm_order` POSTs to `/orders/{id}/confirmation` (asserted against the
  mocked transport — the real endpoint is never called).
- `cancel_order` DELETEs `/orders/{id}` and synthesizes a result on 204.
- `estimate_costs` polls until `completed`; raises on `failed` including the
  failure reasons; raises on timeout naming the task ID.
- `summarize_orders` flattens nested costs safely when `costs` is absent.

### `core/mockups.py`
- `create_task` rejects empty variant lists and missing image URLs.
- `create_task` builds the nested `products[].placements[].layers[]` payload.
- `wait_for_task` raises on `failed` and on timeout.
- `extract_mockup_urls` pulls both primary and `extra` URLs, and returns `[]` for
  an empty or malformed body.

### `core/catalog.py`, `core/shipping.py`, `core/files.py`
- `summarize_products` / `summarize_variants` / `summarize_rates` /
  `summarize_countries` handle empty and partial payloads without `KeyError`.
- `calculate_rates` rejects an empty item list.
- `calculate_tax` targets v1 with a nested `recipient`.
- `files.list_added` labels itself `session-local` and carries the explanatory note.

### CLI-level guards (via `CliRunner`, no network)
- `orders confirm` without `--yes` exits non-zero and does not construct a backend.
- `orders cancel` without `--yes` exits non-zero.
- `--dry-run orders confirm --yes` reports the would-be request and makes no call.
- `--json` emits parseable JSON on both success and error paths.
- `config set` rejects unknown keys.
- `_parse_ids` rejects non-integer input with the offending token named.

## E2E Test Plan (`test_full_e2e.py`)

Requires a real `PRINTFUL_API_KEY`. These call the live API.

**Read-only, free, idempotent — always run:**
- `ship countries` returns a non-empty country list including `US`.
- `catalog products --limit 3` returns 3 products, each with an integer ID.
- `catalog product 71` returns product 71 with a name and variant count.
- `catalog variants 71` returns variants carrying size/color.
- `catalog variant-price <id>` returns pricing for a real variant discovered in the
  previous step (not hardcoded).
- `catalog categories` returns categories with IDs and titles.
- `catalog size-guide 71` returns size tables.
- `store list` returns the stores the token can reach.
- `orders list --limit 3` succeeds (may legitimately be empty).
- `test` reports `ok: true`.

**Live write, but free — draft only:**
- Build a draft via the CLI, `orders create`, assert a draft order comes back with
  status `draft` and an integer ID. **The created draft is then cancelled** so the
  suite leaves no residue — cancellation of a *draft* is free and non-destructive
  to anything the user cares about, unlike cancelling a confirmed order.
- `orders estimate` against the draft returns costs.
- `ship rates` returns at least one rate for a US destination.

**Never called against the live API:**
- `orders confirm` — would charge the account.
- `orders cancel` on any order this suite did not itself create.
- `mockup create` — rate-limited and consumes the account's daily file budget.
  Gated behind `PRINTFUL_E2E_MOCKUPS=1`; off by default.

**CLI subprocess tests (`TestCLISubprocess`):**
Resolved with `_resolve_cli("cli-anything-printful")`, no `cwd` set, so the
installed console script is exercised as a user or agent would invoke it.
- `--help` and `--version` exit 0.
- `--json ship countries` emits parseable JSON.
- `--json catalog products --limit 2` emits parseable JSON with 2 rows.
- Full draft workflow through the installed binary against a temp session file:
  `draft recipient` → `draft add-item` → `draft show` → `ship rates`.
- `orders confirm` without `--yes` exits non-zero through the real binary.

## Realistic Workflow Scenarios

### Workflow 1: "Price a two-shirt order before committing"
**Simulates:** a seller checking landed cost before placing an order.
**Operations chained:** `catalog products` → `catalog variants` →
`catalog variant-price` → `draft recipient` → `draft add-item` (x2) →
`ship rates` → `orders estimate`.
**Verified:** each step returns usable IDs for the next; the final estimate carries
a currency and a numeric total; no order is created.

### Workflow 2: "Draft an order and walk away"
**Simulates:** assembling an order across several shell invocations.
**Operations chained:** `draft recipient` → (new process) `draft add-item` →
(new process) `draft show` → `orders create` → `orders get` → cleanup.
**Verified:** session state survives process boundaries; the created order has
status `draft`; `orders get` round-trips the ID.

### Workflow 3: "Refuse to spend money by accident"
**Simulates:** an agent that tries to confirm an order without authorization.
**Operations chained:** `orders confirm <id>` (no flag) → `--dry-run orders confirm
<id> --yes` → assert no API call in either case.
**Verified:** non-zero exit and an explanatory error on the first; a `dry_run`
report and zero network traffic on the second.

### Workflow 4: "Recover file IDs with no list endpoint"
**Simulates:** needing a previously uploaded design's ID.
**Operations chained:** `files add` → `files list` → `files get <id>`.
**Verified:** `files list` is labelled `session-local`, contains the added record,
and the ID round-trips through a real `files get`. Gated with the mockup tests
since it writes to the user's file library.

## Known coverage gaps, accepted deliberately

| Gap | Why | Mitigation |
|---|---|---|
| `orders confirm` never hits the live API | Charges real money | Unit-tested against a mocked transport; the `--yes` guard is tested through the installed binary |
| `orders cancel` only used on drafts this suite created | Destructive | Same |
| `mockup create` off by default | 2 req/60s on new stores; 20k file/24h cap | Opt in with `PRINTFUL_E2E_MOCKUPS=1` |
| `store stats` not asserted on values | Depends on the account having sales history | Call is exercised; only the response shape is checked |
| `sync`, `store templates`, `ship tax` | v1 endpoints requiring specific scopes and a Printful-platform store | Exercised if reachable; scope/platform errors are asserted to be reported cleanly rather than crashing |

---

# Part 2: Test Results

Two runs: an initial one with no credentials, then a full live run after the
operator supplied a token. **The live run found five defects that every
docs-derived assumption and mocked test had missed.** They are recorded below
because they are the whole argument for the harness spec's insistence on real
backend E2E.

## Final run

```bash
export PRINTFUL_API_KEY=...            # supplied by the operator
export PRINTFUL_STORE_ID=1135966       # Fatherhood University
PATH="$PWD/.venv/bin:$PATH" CLI_ANYTHING_FORCE_INSTALLED=1 \
  python -m pytest agent-harness/cli_anything/printful/tests/ -v -s
```

```
145 passed, 3 skipped in 19.82s
```

`_resolve_cli` confirmed the installed console script was used:

```
[_resolve_cli] Using installed command: /Volumes/Containers/printful-mcp/.venv/bin/cli-anything-printful
```

| Suite | Result |
|---|---|
| `test_core.py` — unit, mocked transport | **122 passed** (0.37s, no network) |
| `test_full_e2e.py` — live API + subprocess | **23 passed** |
| `test_full_e2e.py` — opt-in mockups | **3 skipped** (`PRINTFUL_E2E_MOCKUPS` unset) |
| **Total** | **145 passed, 3 skipped, 0 failed** |

Live artifacts printed during the run:

```
  Countries: 239 of 239
  Products: [1, 2, 3]
  Stores: [(905397, 'Personal orders'), (1135966, 'Fatherhood University'), (6751340, 'Square store')]
  404 surfaced as: Product 99999999 does not exist or is inactive.
  Rates: [('Flat Rate (Estimated delivery: Sep 23–25) ', '4.95', 'USD')]
  Draft order created: 176657491
  Draft order 176657491 cancelled (cleanup)
  Estimated total: 20.43 USD
```

## Defects the live run found

Each is now locked in by a regression test built from the captured response body.

### 1. v2 errors are not RFC 9457 — every API error read as "Unknown error"

The v2 docs describe problem details (`detail`/`title`). The live API returns the
v1-style envelope, for 400 and 404 alike:

```json
{"data": "Product 99999999 does not exist or is inactive.",
 "error": {"reason": "NotFound", "message": "Product 99999999 does not exist or is inactive."}}
```

Reading only `detail`/`title` collapsed every v2 error to "Unknown error", which
masked the next three defects — they were invisible until this was fixed.

`_extract_error_message` now tries every known shape regardless of version.
Regression: `test_v2_error_reads_v1_style_envelope`,
`test_v2_404_reads_v1_style_envelope`, `test_v2_error_never_degrades_to_unknown`.

**The same bug exists in the parent repo at `src/printful_mcp/client.py:141`.**
Not fixed here — out of scope for this harness.

### 2. `/v2/countries` is paginated; the US was missing

Returns 20 of 239 rows by default, and `US` is not in the first page
alphabetically. The CLI reported that Printful does not ship to the United
States. `list_countries` now walks every page. Regression:
`TestCountriesPagination` (6 tests) plus a live assertion that the returned count
equals `paging.total`.

### 3. Catalog order items require `placements`

`Property `placements` is required` — Printful will not accept an order item with
no artwork, because it has nothing to print. The draft model allowed it and
failed only at submission. `missing_fields()` now reports it per item with the
exact command to fix it, and `summary()` exposes `items_without_design`.

The asymmetry matters and is deliberately preserved: **shipping rates can be
quoted without artwork**, so a draft is `priceable` before it is `complete`.
Regression: 7 tests in `TestDraftOrder` plus live coverage of both paths.

### 4. `/v2/shipping-rates` rejects an item without `source`

`Property `/order_items/0/source` must be of type `string`, `null` provided`.
`calculate_rates` now defaults `source` to `catalog` without mutating the
caller's list. Regression: `test_rates_defaults_missing_source`,
`test_rates_preserves_explicit_source`, `test_rates_does_not_mutate_caller_items`.

### 5. Shipping rate rows are keyed `shipping` / `shipping_method_name`

Not `id` / `name`. `summarize_rates` produced a table of nulls for the two most
important columns. Both spellings are now accepted, live first. Regression:
`test_summarize_rates_reads_live_keys`, `test_summarize_rates_falls_back_to_id_name`.

### Also: a test that was too weak to catch defect 1

`test_bad_product_id_errors_cleanly` asserted only that *a* message existed —
and "Unknown error" is a message, so it passed throughout. It now asserts the
API's real text appears and that the message is never the placeholder.

## Coverage gaps, unchanged

| Gap | Status |
|---|---|
| `orders confirm` never called live | **By design.** Charges money. Endpoint asserted against a mocked transport; the `--yes` guard verified through the installed binary. |
| `orders cancel` only on drafts the suite created | **By design.** The live run created one draft and cancelled it; nothing else was touched. |
| `mockup create` | **Skipped by default.** 2 req/60s on new stores; 20k files/24h cap. Enable with `PRINTFUL_E2E_MOCKUPS=1`. |
| `store stats`, `ship tax`, `store templates`, `sync` | **Not asserted on values.** Need sales history, a Printful-platform store, and specific token scopes. |

The earlier gap "live response shapes unverified" is now **closed** for catalog
products, variants, categories, countries, stores, shipping rates, orders, and
error envelopes — all checked against live responses. It remains open only for
the four v1/scope-dependent endpoints above and for mockups.

## Test account note

The live write path ran against store **1135966 (Fatherhood University)**, chosen
by the operator. Each run creates exactly one draft order and deletes it
(`DELETE /v2/orders/{id}` → 204). Drafts are never charged.
