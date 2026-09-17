# Cull, Distribute, and Close the Coverage Gap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this fork installable in one command, documented truthfully, and covered by tests that can fail — closing the debt plans 1 and 2 deliberately deferred.

**Architecture:** Nothing structural changes. `printful_core` keeps the request-spec design, the MCP server and CLI keep their adapters. This plan adds a lint gate the codebase actually agrees with, assertions for renderers that currently render unasserted, the distribution manifests that make the repository serve itself as a plugin marketplace, and CI that catches the class of break this repository shipped with for the entire life of `mcp` 2.x.

**Tech Stack:** Python 3.10+, pytest, ruff, GitHub Actions, `uvx`, Claude Code plugin manifests.

**Spec:** `docs/superpowers/specs/2026-09-16-printful-merger-design.md` — phases 5 and 6 (§ The cull, § Distribution, § Continuous integration), plus the deferred items recorded in `.superpowers/sdd/2026-09-16-mcp-server-on-the-core/progress.md`.

## Global Constraints

Every task's requirements implicitly include this section.

- **Run pytest as `.venv/bin/python -m pytest`.** A bare `python -m pytest` resolves to the system interpreter, whose global site-packages registers a `langsmith` plugin that crashes in `pytest_cmdline_parse` before collecting anything. That traceback is the interpreter, not this repository.
- **`env -u PRINTFUL_API_KEY` does not prove the offline suite is credential-free.** `server.py` calls `load_dotenv()` at import, so `.env` puts the key straight back. Use `mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env`, and **confirm `.env` is restored** — it holds a real key. Never print, echo, or commit its contents.
- **Clear `__pycache__` and verify zero after every mutation you revert:**
  ```bash
  find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
  find src -name '__pycache__' -type d | wc -l    # must print 0
  ```
  A size-preserving edit — swapping two adjacent quoted words — outlived its own revert on the previous plan and corrupted a measurement two tasks later, because CPython's staleness check is mtime plus size. **Do not use `find … -exec rm -rf {} + 2>/dev/null`**; it errors descending into what it deletes, removes nothing, and prints nothing.
- **Run git through `rtk proxy git …`.** A hook rewrites plain `git status --porcelain` in this environment and returns the literal string `ok` instead of real output.
- **No `Co-Authored-By` trailer** naming an agent or model in any commit message.
- **`printful_confirm_order` must NEVER be called against the live API.** It submits an order for fulfillment and charges a real account. It is asserted only against fake transports.
- **Do not run the full `pytest -m live` selection casually.** It creates and cancels a real draft order. `src/printful_mcp/tests/test_live_mcp.py` alone is read-only plus a no-charge estimation task. The live gate needs `set -a; . ./.env; set +a; export PRINTFUL_STORE_ID=<store>`.
- **Mockup creation stays opt-in behind `PRINTFUL_E2E_MOCKUPS=1`.** Printful rate-limits new stores to 2 requests per 60 seconds with a 60-second lockout. Do not set the flag to make more tests run.
- **No deletion in this plan reaches the upstream pull request.** The cherry-pick branch `fix/mcp2-pin-v2-errors-order-items` stays at `b03c0cc`. Do not move the `upstream-base` tag (an annotated tag whose object is `a158d18`, pointing at commit `2a5eacd`), do not rebase, do not amend.
- **This plan states no predicted test counts.** Report the real number you observe. Five predicted counts in plan 1 proved wrong, and a plan-era number becomes a deletion target.

### The state this plan starts from

Plans 1 and 2 already did part of the spec's cull. Do not re-delete what is gone:

| Spec target | State |
|---|---|
| `src/printful_mcp/client.py` | **already deleted** (plan 2) |
| `agent-harness/`, CLI `utils/printful_backend.py`, `utils/repl_skin.py` | **already gone** (plan 1) |
| `.serena/` in `.gitignore` | **already done** |
| `test_server.py`, `test_comprehensive.py`, `test_complete.py` | present, dead (import the deleted client) |
| `run-tests.sh`, `examples.py`, `TESTING.md`, `PRINTFUL.md` | present |
| `.claude-plugin/`, `.mcp.json`, `skills/`, `.codex-plugin/`, `scripts/`, `.github/`, `.pre-commit-config.yaml` | **do not exist** |

### Two spec statements this plan overrides, and why

**1. The spec says `.agents/AGENTS.md` and `.gemini/GEMINI.md` symlink to `.claude/CLAUDE.md`.** That file no longer exists. `.gitignore:118-120,134` excludes `.agent/`, `.agents/`, `.claude/` and `.gemini/`, so every one of those paths is local-only and reaches no clone. The agent contract now lives at the repository root as a tracked `CLAUDE.md`, by the user's explicit decision during plan 2. This plan ships a tracked root `AGENTS.md` instead of a symlink into an ignored directory.

**2. The spec's CI `server-boots` job asserts "the expected tool count."** Plan 2 established that the count is a consequence of the builder→tool mapping, not a target — `test_server.py` asserts the mapping by set difference in three directions, and each failure names the offending symbol. The CI job runs that test rather than hardcoding 32, so a legitimate new tool does not fail CI for being new.

### The lint decision this plan makes

`ruff check src/` on default rules reports **447 errors**. That number is misleading and the plan does not chase it:

| Rule family | Count | Disposition |
|---|---|---|
| `UP006` non-pep585-annotation | 181 | **Not enabled.** `Dict[str, Any]` → `dict[str, Any]` across 28 files. Zero behavior change, and it fights a style the codebase applies consistently. |
| `UP045` non-pep604-annotation-optional | 105 | **Not enabled.** Same. |
| `F541` f-string-missing-placeholders | 75 | **Not enabled.** 67 are `markdown.py`'s `f""` blank-line idiom, deliberate for visual alignment inside lists of f-strings. |
| `UP035` deprecated-import | 41 | **Not enabled.** Follows from the two above. |
| everything else | **52** | **Enabled and fixed** — 17 auto-fixable. |

Measured at `a4327ee` with the exact config Task 1 installs, not with ruff's defaults. The four rows above are counted on defaults; the 52 is what remains once they are off and the rest of the `select` list is on, so the numbers are not a subtraction and will not add up to 447.

`ruff format` reports "57 files would be reformatted", which reads as enormous and is not: the diff is **114 changed lines** across those files, roughly two per file. The plan adopts it.

A linter should encode what a project believes. Enabling a rule family that rewrites every signature in the repository imports a different project's opinion and buries real findings under churn.

---

### Task 1: A lint gate the codebase agrees with

**Files:**
- Modify: `pyproject.toml` (add `[tool.ruff]`)
- Modify: whatever the 52 findings and the formatter touch

**Interfaces:**
- Consumes: nothing.
- Produces: `ruff check src/` and `ruff format --check src/` both exit 0, which Task 11's CI job depends on.

`ruff` is declared in the `dev` extra but is **not installed in `.venv`** — `pip install -e ".[dev]"` was never fully run here. Install it first:

```bash
.venv/bin/python -m pip install 'ruff>=0.1.0'
.venv/bin/python -m ruff --version
```

- [ ] **Step 1: Add the configuration**

Append to `pyproject.toml`, after `[tool.pytest.ini_options]`:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I", "B", "SIM", "DTZ", "C4", "PIE", "ISC", "BLE", "RUF"]
# F541 flags `f""`. Sixty-seven of the seventy-five are markdown.py's blank-line
# idiom inside lists of f-strings, where the prefix keeps a column aligned. The
# rule is correct and the code is deliberate, so the rule is off rather than the
# code changed.
ignore = ["F541"]
```

**The `UP` family is deliberately not selected.** It reports 327 findings — `Dict[str, Any]` → `dict[str, Any]` and `Optional[X]` → `X | None` across 28 files — for zero behavior change, against a style this codebase applies consistently. A linter should encode what the project believes; enabling that family imports a different project's opinion and buries the real findings under churn. `line-length = 100` rather than the default 88 for the same reason: 100 lines in `src/` exceed 88, and 12 exceed 100.

- [ ] **Step 2: Record the baseline before changing anything**

```bash
.venv/bin/python -m ruff check src/ --statistics
.venv/bin/python -m ruff format --check src/
```

Expected: **52 findings, 17 auto-fixable**, and **57 files would be reformatted**. Paste both into your report. If your numbers differ from these, say so — they were measured at `a4327ee` and a difference means something moved.

- [ ] **Step 3: Apply the formatter**

```bash
.venv/bin/python -m ruff format src/
rtk proxy git diff --stat
```

"57 files" reads as enormous and is not: the diff is **114 changed lines**, roughly two per file. Confirm that — if your diff is materially larger, stop and report it rather than committing a reformat you have not understood.

- [ ] **Step 4: Run the suite before touching a single lint finding**

```bash
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
```

The formatter must not change behavior. A failure here is a formatter bug or a test depending on source layout, and either one is worth knowing before 52 more edits land on top.

- [ ] **Step 5: Take the auto-fixes, then read every one**

```bash
.venv/bin/python -m ruff check src/ --fix
rtk proxy git diff
```

17 are auto-fixable — unsorted imports, unused imports, `PIE807`, `C408`. **Read the diff.** An unused-import removal is safe; an import that exists for a re-export side effect is not, and ruff cannot tell them apart.

- [ ] **Step 6: Judge the remainder one at a time**

The rest need a decision, not a fix. Three families matter:

- **`BLE001` blind-except (7)** — `except Exception` swallowing everything. Each one is either a real defect or a deliberate boundary. `printful_mcp/transport.py`'s `_close_transport` catches `RuntimeError` on purpose, documented in its own comment, because at interpreter shutdown there may be no usable event loop and the socket goes with the process. That reasoning is in the code; do not delete it to satisfy a linter. Where a blind except is *not* justified, narrow it or add `noqa` **with the reason on the same line** — never a bare `noqa`.
- **`B904` raise-without-from-inside-except (7)** — a re-raise inside `except` that drops the original cause. This is a real quality rule: `raise PrintfulError(...) from e` preserves the chain a debugger needs. Apply it unless the original is genuinely noise, and say which you judged noise.
- **`SIM115` open-without-context-manager (4)**, **`DTZ005` naive `datetime.now()` (2)** — fix both; they are ordinary defects.

For each finding you suppress rather than fix, the report names it and why. A `noqa` count that nobody can explain is worse than a lint failure.

- [ ] **Step 7: Verify both gates and commit**

```bash
.venv/bin/python -m ruff check src/
.venv/bin/python -m ruff format --check src/
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
```

Both ruff commands exit 0. Report the test number you observe.

```bash
rtk proxy git add pyproject.toml src/
rtk proxy git commit -m "build: configure ruff to this codebase's conventions and apply it"
```

---

### Task 2: The cull

**Files:**
- Delete: `test_server.py`, `test_comprehensive.py`, `test_complete.py`, `run-tests.sh`, `examples.py`, `PRINTFUL.md`, `TESTING.md`
- Modify: every file that references them

**Interfaces:**
- Consumes: Task 1's formatting.
- Produces: a repository root with nothing in it that fails when run.

Seven files, each justified by name. The rule from the previous plan holds and is stronger than it looks: **a deletion is justified by naming its successor and the case it covered, never by a count.** The previous plan deleted a test against a successor table that named two tests covering neither half of its case, and a real coverage gap shipped for two tasks before a reviewer caught it.

- [ ] **Step 1: Confirm what each file is before deleting it**

```bash
rtk proxy git grep -ln "test_server\|test_comprehensive\|test_complete\|run-tests\|examples\.py\|PRINTFUL\.md\|TESTING\.md" -- ':!docs/superpowers' ':!.superpowers'
```

Every hit is a reference you must update in Step 3. Paste the list into your report.

**Note the name collision:** the root `test_server.py` is being deleted, and `src/printful_mcp/tests/test_server.py` is the parity suite that must stay. They are different files. Check the path on every command.

- [ ] **Step 2: Delete, with the successor named for each**

| Deleted | Superseded by | The case it covered |
|---|---|---|
| `test_server.py` (root) | `src/printful_mcp/tests/` | 6 smoke tests against the live API; the offline suite covers every one of those tools against fakes, and `test_live_mcp.py` covers the live path |
| `test_comprehensive.py` | `src/printful_mcp/tests/test_*.py` | every tool wrapper; the per-domain modules assert the `Request` each builds |
| `test_complete.py` | `src/printful_mcp/tests/test_live_mcp.py` | end-to-end with real data — and it is pinned to store `14690720`, which belongs to the original author, so it cannot pass here at all |
| `run-tests.sh` | `pytest` | an interactive `read -p` menu that hangs every non-interactive caller |
| `examples.py` | `README.md` | 202 lines of docstrings; running it prints "see comments above" |
| `PRINTFUL.md` | `docs/superpowers/` | harness framing from a tool that is no longer in this repository |
| `TESTING.md` | `README.md` + `CLAUDE.md` | its runnable content is four snippets, repaired in the previous plan; its remaining Methods 1–3 still teach ad-hoc `test_manual.py` scripts and its "Recommended Testing Flow" is a pre-suite manual checklist |

```bash
rtk proxy git rm test_server.py test_comprehensive.py test_complete.py run-tests.sh examples.py PRINTFUL.md TESTING.md
```

**Before you run that:** `TESTING.md` is the one with content worth rescuing. Read it first and move anything still true into `README.md`'s testing section or `CLAUDE.md`. Say in your report what you moved and what you judged dead.

- [ ] **Step 3: Fix every reference**

`README.md`, `API_TOKEN_SETUP.md` and `API_SCOPES_REFERENCE.md` reference the deleted scripts. `pyproject.toml`'s `testpaths` comment explains why the root scripts are excluded — that reason disappears with the files, so the comment goes too, and `testpaths` itself stays as the list of real suites.

`CLAUDE.md` carries a paragraph headed **"The three root-level `test_*.py` scripts are dead"**. Delete that paragraph; it documents files that no longer exist.

- [ ] **Step 4: Prove nothing that remains is broken**

```bash
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
.venv/bin/python -m ruff check src/
rtk proxy git grep -n "test_comprehensive\|test_complete\|run-tests\|examples\.py\|PRINTFUL\.md\|TESTING\.md" -- ':!docs/superpowers' ':!.superpowers'
```

That last grep must return nothing. A reference to a deleted file in a shipped document is the defect this plan exists to stop shipping.

- [ ] **Step 5: Commit**

```bash
rtk proxy git add -A
rtk proxy git status --porcelain
rtk proxy git commit -m "chore: delete the superseded scripts and the docs that described them"
```

Paste the `status --porcelain` output into your report so the staging decision is visible.

---

## Tasks 3–5: the renderer coverage gap

The final review of the previous plan measured it: **216 of 279 key mutations across `format/markdown.py` survive the whole suite.** Then the final fix round converted 95 unguarded subscripts to `.get` with a default, which closed the crash surface and *enlarged* this one — those 95 defaults are now reachable output that nothing asserts.

A renderer defect is silent by construction. `row.get('catalog_product_id', 'N/A')` against an API that sends `product_id` renders `N/A` forever: valid markdown, no error, no failing test. That exact defect shipped in the previous plan and was caught only by a live call.

**These tests go in `src/printful_core/tests/test_format_markdown.py`, and they call the renderers directly.** The renderers are pure functions of a body; routing through a tool and a fake transport to reach one adds a transport, an input model and an async boundary to a test whose subject is a string. Task 6 covers the tool-level branch separately.

### The bar, identical in all three tasks

Assert **every value the renderer prints**, not one of them. A test asserting one field of eight leaves seven mutable in silence, and "the renderer is covered" then reads as true.

**Each test is named for what a caller loses**, not for the function. `test_a_category_row_shows_the_id_a_caller_needs_to_drill_into`, not `test_categories`.

**Discrimination is proved per field**, and the mutation is a key rename inside the renderer — never a signature change, which raises `TypeError` and proves nothing:

```bash
# in markdown.py, change row.get('title', …) to row.get('titel', …)
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
.venv/bin/python -m pytest -q src/printful_core/tests/test_format_markdown.py
# expect a failure naming that field, then restore and clear bytecode again
```

Report the assertion text, not the red count. **A test that fails by raising inside the renderer has not been shown to discriminate** — its assertion never ran. Both no-failure cases look identical too: the field is genuinely unguarded (a real gap), or the mutation changed nothing observable (a bad mutation). Say which you found.

Clearing bytecode between mutations is not optional here. A key rename that preserves byte length — `title` → `titel` — is exactly the mutation that outlived its revert on the previous plan and corrupted a measurement two tasks later.

---

### Task 3: Renderer coverage — catalog and shipping

**Files:**
- Create: `src/printful_core/tests/test_format_markdown.py`
- Modify: `src/printful_core/format/markdown.py` only if a field proves wrong

**Interfaces:**
- Consumes: `printful_core.format.markdown`.
- Produces: the test module Tasks 4 and 5 extend.

Eleven renderers. Fields, extracted from the source by AST — these are what each one prints:

| Renderer | Reached by | Fields it prints |
|---|---|---|
| `product` | `printful_get_product` | `id`, `name`, `type`, `brand`, `variant_count`, `description`, `techniques[].key`/`display_name`/`is_default`, `placements[].placement`/`technique`, `is_discontinued` |
| `products` | `printful_list_catalog_products` | `paging.total`/`offset`/`limit`, rows: `id`, `name`, `type`, `variant_count`, `techniques[].key` |
| `variants` | `printful_list_variants` | `paging.total`, rows: `id`, `name`, `size`, `color`, `color_code` |
| `variant_prices` | `printful_get_variant_prices` | `currency`, `product`/`variant`, `techniques[].technique_display_name`, `placements[].title`/`price` |
| `availability` | `printful_check_availability` | `catalog_variant_id`, `techniques[].technique`, `selling_regions[].name`/`availability` |
| `categories` | `printful_list_categories` | `paging.total`, rows: `id`, `title`, `parent_id` |
| `category` | `printful_get_category` | `id`, `title`, `parent_id`, `image_url` |
| `size_guide` | `printful_get_size_guide` | `size_tables[].type`/`description`/`unit`, `measurements[].type_label`/`values[].size`/`value`/`min_value`/`max_value` |
| `rates` | `printful_calculate_shipping` | `shipments[].shipping_method_name`/`rate`/`currency`/`min_delivery_days`/`max_delivery_days`/`min_delivery_date`/`max_delivery_date`/`customs_fees_possible`/`departure_country` |
| `countries` | `printful_list_countries` | rows: `name`, `code`, `states[].name`/`code` |
| `tax` | `printful_calculate_tax` | `required`, `rate`, `shipping_taxable` |

- [ ] **Step 1: Create the module with two worked tests**

```python
"""What each renderer prints, asserted field by field.

A renderer defect is silent: `.get` with a default turns a wrong key into
'N/A' rather than an exception, so the tool returns valid markdown that is
missing the one value the caller needed. Only an assertion on the rendered
value catches it, which is why each test below asserts every field its
renderer prints rather than one of them.

These call the renderers directly. They are pure functions of a body; a
transport and an input model would add two boundaries to a test whose
subject is a string.
"""
from printful_core.format import markdown


def test_a_category_row_carries_the_id_a_caller_drills_into():
    """`printful_list_categories` is how a caller finds the id that
    `printful_get_category` needs. Rename the key and the caller gets a list
    of titles with no way to act on any of them -- and no error saying so.
    """
    out = markdown.categories({
        "data": [{"id": 24, "title": "Men's clothing", "parent_id": 0}],
        "paging": {"total": 1},
    })
    assert "24" in out
    assert "Men's clothing" in out
    assert "1" in out


def test_a_tax_answer_distinguishes_zero_from_not_required():
    """"Tax required: no" and "Rate: 0" mean different things to a seller.

    `required` is a boolean the renderer turns into yes/no, and `rate` is a
    number that can legitimately be zero. A renderer reading the wrong key
    gets a falsy default and prints "no" for a destination that does charge
    tax, which is a wrong answer shaped like a right one.
    """
    out = markdown.tax({"required": True, "rate": 0.0825, "shipping_taxable": True})
    assert "yes" in out.lower()
    assert "0.0825" in out
```

- [ ] **Step 2: Run them and watch them pass**

```bash
.venv/bin/python -m pytest -q src/printful_core/tests/test_format_markdown.py
```

- [ ] **Step 3: Prove both discriminate, field by field**

For each field asserted above, rename its key in `markdown.py`, clear bytecode, run, confirm the failure names that field, restore, clear bytecode. Six mutations for the two tests. Paste the assertion text of each into your report.

- [ ] **Step 4: Write the remaining nine renderers to the same bar**

One test per renderer, following the pattern in Step 1: a body containing every field from the table, a docstring naming what the caller loses, and an assertion per field. Where a renderer has a branch — `product`'s `is_discontinued`, `countries`' nested `states`, `rates`' `customs_fees_possible` — cover both sides; a branch asserted on one side is half a test.

`size_guide` is the awkward one: it nests `size_tables[].measurements[].values[]` three deep, and a fixture that stops at two levels renders an empty table while passing a shallow assertion. Build it three deep and assert on a leaf value.

- [ ] **Step 5: Prove every new test discriminates**

Same mutation loop, one per asserted field. This is the bulk of the task and it is the point of the task — a renderer test that has not been mutated is a renderer test that might assert nothing.

Report a table: renderer, field mutated, assertion text of the failure. Where a mutation produced no failure, say which of the two reasons applies.

- [ ] **Step 6: Run everything and commit**

```bash
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
.venv/bin/python -m ruff check src/ && .venv/bin/python -m ruff format --check src/
rtk proxy git add src/printful_core/
rtk proxy git commit -m "test: assert what the catalog and shipping renderers print"
```

---

### Task 4: Renderer coverage — orders and mockups

**Files:**
- Modify: `src/printful_core/tests/test_format_markdown.py`

**Interfaces:**
- Consumes: Task 3's module and its conventions.

Eight renderers, and the highest-stakes ones in the module: `order` is reached by four tools including `printful_confirm_order`, which charges a real account.

| Renderer | Reached by | Fields it prints |
|---|---|---|
| `order` | `create_order`, `get_order`, `confirm_order`, `update_order` | `id`, `status`, `external_id`, `created_at`, `updated_at`, `recipient.name`/`address1`/`city`/`state_code`/`zip`/`country_name`/`country_code`, `costs.currency`/`subtotal`/`shipping`/`tax`/`total`, `order_items[].name`/`catalog_variant_id`/`quantity`/`price`, `calculation_status` |
| `orders` | `printful_list_orders` | `paging.total`/`offset`/`limit`, rows: `id`, `status`, `external_id`, `created_at`, `costs.currency`/`total`, `order_items` |
| `order_items` | `printful_list_order_items` | rows: `id`, `name`, `catalog_variant_id`, `quantity`, `price`, `currency` |
| `shipments` | `printful_list_order_shipments` | rows: `id`, `carrier`, `service`, `tracking_number`, `tracking_url`, `shipped_at` |
| `estimate` | `printful_get_estimation_task` | `costs.currency`/`subtotal`/`shipping`/`tax`/`total`, `failure_reasons` |
| `mockup_task` | `printful_get_mockup_task` | `status`, `catalog_variant_mockups[].catalog_variant_id`/`mockups[].placement`/`style_id`/`mockup_url`/`display_name`, `failure_reasons`, `detail` |
| `mockup_styles` | `printful_list_mockup_styles` | rows: `id`, `name`, `placement`, `technique` |
| `mockup_templates` | `printful_list_mockup_templates` | rows: `id`, `placement`, `technique`, `print_area_width`, `print_area_height`, `image_url` |

- [ ] **Step 1: Cover `order` first, and cover its thin-body branch**

`order` prints five fields with `.get(..., 'unknown')` or `.get(..., 'N/A')` defaults — `id`, `status`, `created_at`, `updated_at`, `external_id` — because the previous plan converted them from unguarded subscripts after a 204 response crashed four tools. That conversion is currently asserted only by `test_empty_bodies.py`, which checks a `str` comes back and never that it says anything true.

```python
def test_a_confirmed_order_reports_the_id_the_caller_must_quote():
    """printful_confirm_order charges the account, and its output is the
    caller's receipt. The id is the only handle on that charge -- a renamed
    key renders 'unknown' and the caller has been billed for an order they
    cannot look up.
    """
    out = markdown.order({
        "id": 98765, "status": "pending", "external_id": "ext-1",
        "created_at": "2026-01-01", "updated_at": "2026-01-02",
        "recipient": {"name": "A Buyer", "address1": "1 Main St", "city": "SF",
                      "state_code": "CA", "zip": "94107",
                      "country_name": "United States", "country_code": "US"},
        "costs": {"currency": "USD", "subtotal": 20.0, "shipping": 5.0,
                  "tax": 1.5, "total": 26.5},
        "order_items": [{"name": "Tee", "catalog_variant_id": 4012,
                         "quantity": 1, "price": 20.0}],
        "calculation_status": "done",
    })
    for expected in ("98765", "pending", "ext-1", "A Buyer", "1 Main St",
                     "United States", "26.5", "Tee", "4012"):
        assert expected in out, f"{expected!r} missing from:\n{out}"


def test_an_empty_order_body_degrades_without_claiming_a_wrong_id():
    """A 204 or empty 2xx reaches this renderer as {}. It must not invent an
    id: 'unknown' is honest, a stale or defaulted number is not.
    """
    out = markdown.order({})
    assert "unknown" in out
    assert isinstance(out, str)
```

- [ ] **Step 2: Prove the loop closes on the field that matters**

Rename `id` to `ident` in `markdown.order`, clear bytecode, run. `test_a_confirmed_order_reports_the_id_the_caller_must_quote` must fail on its own assertion naming `'98765'`. Restore, clear bytecode. Paste the assertion text.

Then confirm `test_empty_bodies.py` **stays green** under that same mutation — that is what demonstrates the gap this task closes, rather than asserting it.

- [ ] **Step 3: Write the remaining seven**

Same bar as Task 3: every field, a caller-loss docstring, both sides of every branch. `mockup_task`'s three states (`pending`, `completed`, `failed`) are three tests or one parametrized test, not one fixture — the failure path prints `failure_reasons` and the success path prints `mockup_url`, and a fixture that exercises one leaves the other unasserted.

- [ ] **Step 4: Prove every new test discriminates, then commit**

```bash
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
.venv/bin/python -m ruff check src/ && .venv/bin/python -m ruff format --check src/
rtk proxy git add src/printful_core/
rtk proxy git commit -m "test: assert what the order and mockup renderers print"
```

---

### Task 5: Renderer coverage — files, stores, sync

**Files:**
- Modify: `src/printful_core/tests/test_format_markdown.py`
- Modify: `src/printful_core/format/markdown.py` — one guard, see Step 3

**Interfaces:**
- Consumes: Tasks 3 and 4.
- Produces: the module complete at 26 renderers.

Seven renderers, and the two that already cost this project a live defect.

| Renderer | Reached by | Fields it prints |
|---|---|---|
| `file_added` | `printful_add_file` | `id`, `status`, `filename`, `url`, `width`, `height`, `dpi`, `size`, `preview_url` |
| `file_detail` | `printful_get_file` | `id`, `status`, `filename`, `mime_type`, `created`, `width`, `height`, `dpi`, `size`, `hash`, `url`, `thumbnail_url`, `preview_url` |
| `stores` | `printful_list_stores` | rows: `id`, `name`, `type` |
| `store_statistics` | `printful_get_store_stats` | `currency`, `profit`, `total_paid_orders`, `printful_costs`, `average_fulfillment_time`, `store_id`, each with `value`/`relative_difference`, plus the `date_from`/`date_to` passed as arguments |
| `store_templates` | `printful_list_store_templates` | `items[]`, `paging.total`, rows: `id`, `title`, `product_id`, `created_at` |
| `sync_products` | `printful_list_sync_products` | `items[]` or a bare list, rows: `id`, `name`, `external_id`, `sync_variants` |
| `sync_product` | `printful_get_sync_product` | `sync_product.id`/`name`/`external_id`/`thumbnail_url`, `sync_variants[].variant_id`/`retail_price`/`currency` |

- [ ] **Step 1: Cover `store_templates` first — it is the one that was wrong**

The previous plan shipped this renderer reading `catalog_product_id` where the API sends `product_id`, and reading a v2 `data`/`paging` envelope off a `version="v1"` request. Both were found by live calls, because a `.get` default cannot raise. Pin both:

```python
def test_a_template_row_shows_the_product_id_not_a_v2_field_name():
    """This renderer shipped reading `catalog_product_id`; the API sends
    `product_id`, so every row printed 'N/A' and nothing failed. The v1
    body also arrives as `items`, not the v2 `data` envelope -- reading
    `data` renders 'Showing 0 templates' for a store that has templates.
    """
    out = markdown.store_templates({
        "items": [{"id": 77, "title": "Summer Tee", "product_id": 71,
                   "created_at": "2026-01-01"}],
        "paging": {"total": 1},
    })
    assert "Summer Tee" in out
    assert "71" in out
    assert "77" in out
    assert "Showing 1 templates" in out


def test_a_bare_list_of_templates_still_renders():
    """v1 hands some collections back as the list itself. `.get` on a list
    raises AttributeError, which is not a PrintfulError and escapes the tool
    as a traceback where an MCP client expects a string.
    """
    out = markdown.store_templates([{"id": 77, "title": "Summer Tee",
                                     "product_id": 71}])
    assert "Summer Tee" in out
```

- [ ] **Step 2: Cover `store_statistics`' argument-passed date window**

It takes `(data, date_from, date_to)` rather than one body, because the header prints the *requested* range and a response body does not carry it back. Assert the rendered header carries the window — the request-level assertion already in `test_small_domains.py` does not reach the rendered text.

- [ ] **Step 3: Fix the `result: null` pair, together**

`sync_products` and `store_templates` both raise `AttributeError` when a v1 body arrives as `{"code": 200, "result": null}` — `_normalize` returns `None` and both call `.get` on it. The previous plan left this deliberately, reasoning the pair should stay symmetric and the shape was unevidenced. **It is still unevidenced** — a repository-wide grep for `"result": *null` finds only the previous plan's own notes.

Fix both, in one edit, because guarding one forks a pair that should match:

```python
    if not data:
        rows, paging = [], {}
    elif isinstance(data, list):
        rows, paging = data, {}
    else:
        rows = data.get('items', [])
        paging = data.get('paging', {})
```

Apply the equivalent to `sync_products`. One test each, asserting a `str` comes back for `None` rather than a raise. If the two renderers' shapes make a single identical guard impossible, say so and keep them as close as the shapes allow — do not invent a third pattern.

- [ ] **Step 4: Write the remaining five, prove discrimination, commit**

```bash
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
.venv/bin/python -m ruff check src/ && .venv/bin/python -m ruff format --check src/
rtk proxy git add src/printful_core/
rtk proxy git commit -m "test: assert what the file, store and sync renderers print"
```

- [ ] **Step 5: Re-measure the gap this task set out to close**

Re-run the mutation sweep the final review used: rename every key literal in `markdown.py` one at a time and count how many survive the suite. Report the number against the review's baseline of **216 of 279 surviving**. That number is the deliverable of Tasks 3–5, and reporting it is how anyone knows whether they worked.

---

### Task 6: The `format="json"` branches

**Files:**
- Create: `src/printful_mcp/tests/toolsamples.py`
- Modify: `src/printful_mcp/tests/test_empty_bodies.py`
- Create: `src/printful_mcp/tests/test_json_format.py`

**Interfaces:**
- Consumes: `test_empty_bodies.py`'s registration scan and its `_SAMPLES` input builder.
- Produces: `toolsamples.py`, importable by any test that needs a minimal valid input per tool.

**Every input model carries `format: Literal["markdown", "json"]`, and every tool body branches on it.** There are **30 such branches across seven tool modules** — orders 10, catalog 8, mockups 3, stores 3, shipping 2, files 2, sync 2. **Five tests in the whole suite pass `format="json"`.** Deleting the branch from `orders.get_order` fails nothing, measured.

The branch is not decorative. `json.dumps(data, indent=2)` is what an agent parses when it needs the body rather than prose, and a tool that silently renders markdown instead hands back something the caller cannot load.

- [ ] **Step 1: Extract the sample-input builder so two tests can share it**

`test_empty_bodies.py` already solves the hard part: scanning `server.py` for registrations and constructing a minimal valid input model per tool. Move that machinery into `src/printful_mcp/tests/toolsamples.py` unchanged — same function names, same `SKIP` dict, same "add one to `_SAMPLES`, do not add the tool to `SKIP`" error — and have `test_empty_bodies.py` import it.

This is a move, not a rewrite. **Capture the suite count before and after and confirm it is identical**; a move that changes a number moved more than it claimed.

- [ ] **Step 2: Write the json test against every tool that has the branch**

```python
"""Every tool's json branch returns the body, not prose.

An agent asking for format="json" is going to parse the result. A tool that
falls through to its markdown renderer hands back something that raises on
json.loads -- and the failure surfaces in the caller, not here, unless this
asserts it.
"""
import json

import pytest

from printful_mcp.tests.toolsamples import TOOLS, build_input, call_tool

# The body every tool is handed. Shallow on purpose: this asserts the branch
# returns the body verbatim, not that any renderer can format it.
BODY = {"data": {"id": 1, "marker": "verbatim-body"}}


@pytest.mark.parametrize("tool", sorted(TOOLS))
async def test_the_json_branch_returns_the_body_and_not_prose(tool, transport):
    params = build_input(tool, fmt="json")
    if params is None:
        pytest.skip(f"{tool} has no format field")
    transport._responses.append(BODY)
    out = await call_tool(tool, transport, params)
    parsed = json.loads(out)
    assert parsed == BODY, f"{tool} returned something other than the body"
```

`build_input(tool, fmt="json")` returns `None` for the tools whose model has no `format` field — `printful_list_countries` takes no arguments at all, and `CreateMockupTaskInput.format` means *image* format (`"jpg"`/`"png"`) and is the documented exception. **Skip those two by that property, not by name**: a name list goes stale silently, a property check does not.

- [ ] **Step 3: Prove it discriminates, on a tool it was not written against**

Delete the `if params.format == "json": return json.dumps(...)` branch from `printful_core`-facing `tools/catalog.py`'s `get_product`, clear bytecode, run. The parametrized case for that tool must fail on `json.loads` or on the equality — report which, and the assertion text. Restore, clear bytecode.

Then do the same for `tools/orders.py`'s `get_order`, which the final review measured as currently unguarded. That one failing is the evidence this task closed a real gap rather than restating a covered one.

- [ ] **Step 4: Run everything and commit**

```bash
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
.venv/bin/python -m ruff check src/ && .venv/bin/python -m ruff format --check src/
rtk proxy git add src/printful_mcp/tests/
rtk proxy git commit -m "test: assert every tool's json branch returns the body"
```

---

### Task 7: The remaining deferred items

**Files:**
- Modify: `src/printful_mcp/tests/test_empty_bodies.py`
- Modify: `src/printful_mcp/tests/test_server.py`, `src/printful_mcp/tests/toolsamples.py`
- Modify: `src/printful_core/format/markdown.py`
- Modify: `src/printful_mcp/tools/mockups.py`

**Interfaces:**
- Consumes: Task 6's `toolsamples.py`.

Four items the previous plan's reviews raised and deferred, each with its evidence already gathered.

- [ ] **Step 1: `assert transport.sent` proves a request went out, not that a read executed**

`test_empty_bodies.py` asserts every registered tool returns a `str` for a `{}` body. The final re-review named its weakness precisely: a tool that short-circuits on a falsy body passes that bar **without ever reaching the renderer**, so the swept `.get` defaults it was written to protect go unexercised.

Strengthen it: assert the returned string is non-empty *and* contains something the renderer would only produce. The renderer prints a heading for every body it is given, so:

```python
    assert out.strip(), f"{tool} returned an empty string for an empty body"
    assert out.lstrip().startswith("#") or out.startswith("Error:") or out.startswith("✓"), (
        f"{tool} returned neither a rendered document nor a readable error:\n{out!r}"
    )
```

If a tool legitimately returns something matching none of those three, that is a finding — report it rather than widening the assertion until it passes. **An assertion widened to accommodate its own failures is the failure mode this repository has produced seven times.**

- [ ] **Step 2: Derive `_TOOL_MODULES` instead of hardcoding it**

`test_server.py` and `toolsamples.py` each carry a hardcoded seven-name allowlist of tool modules. It fails loudly on divergence rather than silently — `test_server.py` globs the endpoints directory, so a new module produces a non-empty set difference — but the failure message misdescribes the cause, reading as an orphaned function rather than "module not in the set."

Replace the literal with a glob of the directory the names come from:

```python
_TOOLS_DIR = _SRC / "printful_mcp" / "tools"
TOOL_MODULES = {p.stem for p in _TOOLS_DIR.glob("*.py") if p.stem != "__init__"}
```

Confirm the derived set equals the current literal before deleting the literal. Then add a module to `tools/` that is not imported anywhere, run, and confirm the failure now names the module rather than a function. Delete the probe module and clear bytecode.

- [ ] **Step 3: `tools/mockups.py:50` reads `body['id']` unguarded**

Guarded by `if not body:` so `{}` is safe, which is why `test_empty_bodies.py` passes. It breaks on a **non-empty** body missing `id` — a 200 carrying a partial task record. Convert it to `.get('id', 'unknown')`, matching the treatment `markdown.order` received, and add a test passing `{"data": {"status": "pending"}}`.

- [ ] **Step 4: Rule on the estimation placements question**

The live API rejects `create_estimation_task` without `placements`: `Property 'placements' is required`. `printful_core.endpoints.orders.create_estimation_task` does not check, so the caller spends a round trip to learn it. The previous plan reported rather than fixed it, because `src/printful_cli/core/orders.py:62` calls the same builder and the constraint was to report core changes that alter CLI behavior.

**That constraint does not bind this plan** — it existed to keep plan 2's blast radius inside the MCP surface. Decide here, and record the decision:

- Adding `_require_placements(items)` to `create_estimation_task` makes both surfaces fail locally with a message naming the offending index, instead of after a round trip.
- It changes CLI behavior: an estimate that previously reached the API and returned the API's message now fails before sending.
- `src/printful_cli/tests/test_core.py:182` already records the same requirement for order submission, so the CLI's own tests understand this shape.

Whichever you choose, **the CLI's live suite is the gate**: if you change the core, `pytest -m live` must still return the CLI's 18 passed / 3 skipped. If it does not, the change altered CLI behavior in a way the plan did not intend — revert it and report.

- [ ] **Step 5: Run both gates and commit**

```bash
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
.venv/bin/python -m ruff check src/ && .venv/bin/python -m ruff format --check src/
```

Then the live gate, once, and report the CLI and MCP numbers separately:

```bash
set -a; . ./.env; set +a
export PRINTFUL_STORE_ID=<store>
.venv/bin/python -m pytest -m live -q
```

```bash
rtk proxy git add -A
rtk proxy git commit -m "test: close the deferred coverage items and rule on estimate placements"
```

---

### Task 8: Every agent-facing surface, made true

**Files:**
- Modify: `.cursor/skills/printful-mcp/SKILL.md`
- Modify: `src/printful_cli/skills/SKILL.md`
- Modify: `.serena/memories/printful-mcp-conventions.md`
- Create: `AGENTS.md` (repository root, tracked)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the 32-tool surface as `mcp.list_tools()` reports it.

Four surfaces tell an agent how to use this repository, and every one of them drifted while the code moved. This is the same failure that put `19 tools` and `get_client()` into the agent contract two plans after both stopped being true, and it is the failure the README's "auto-retry on 429" has carried since before this fork existed.

- [ ] **Step 1: The consuming skill — 13 tools are missing**

Measured at `a4327ee` by diffing the names in the file against `mcp.list_tools()`:

```
documented but nonexistent:  none (printful_mcp is the server name, not a tool)
registered but undocumented: printful_calculate_tax, printful_cancel_order,
  printful_create_estimation_task, printful_get_category,
  printful_get_estimation_task, printful_get_size_guide,
  printful_list_categories, printful_list_mockup_styles,
  printful_list_mockup_templates, printful_list_order_items,
  printful_list_order_shipments, printful_list_store_templates,
  printful_update_order
```

Those are precisely the 13 the previous plan added. Document each to the pattern the file already uses for its existing entries — match its structure rather than inventing a second one.

Two existing entries are wrong and were recorded during plan 1 without being fixed:
- `SKILL.md:237` (`printful_calculate_shipping`) never names its **required** `items_json`. A caller following the document calls it without one.
- The rate-limit and retry language predates the `mcp<2` pin work; check it against `printful_core/errors.py` and `transport.py` rather than against memory.

**Re-run the diff after editing** and paste the result — an empty set in both directions is the deliverable:

```bash
.venv/bin/python - <<'PY'
import re, pathlib, asyncio
from printful_mcp.server import mcp
real = {t.name for t in asyncio.run(mcp.list_tools())}
named = set(re.findall(r'printful_[a-z_]+',
                       pathlib.Path('.cursor/skills/printful-mcp/SKILL.md').read_text()))
print('undocumented:', sorted(real - named))
print('nonexistent :', sorted(named - real - {'printful_mcp'}))
PY
```

- [ ] **Step 2: The CLI skill**

`src/printful_cli/skills/SKILL.md` describes the CLI surface. The CLI's commands did not change in plan 2, but its *backend* did — anything in that file describing `printful_backend.py`, a private HTTP client, or error handling that no longer exists is wrong. Check every claim against `src/printful_cli/`, and fix what is false. Do not rewrite what is true.

- [ ] **Step 3: Serena's project memory**

`.serena/memories/printful-mcp-conventions.md` is agent-facing context, and four of its claims are now false:

| Claim in the file | Reality at `a4327ee` |
|---|---|
| "**216 passed, 21 deselected** as of `a89724a`" | 354 passed, 28 deselected |
| "`testpaths` = `printful_core/tests`, `printful_cli/tests`, `tests`" | `src/printful_mcp/tests` is in the list too |
| "`collect_pages` is sync-only … do **not** make it async" | `collect_pages_async` has existed since plan 1 |
| "README `:44` says 17 tools (actual 19)" | actual is 32, and the README is rewritten in Task 9 |

One claim in it is **correct and was doubted**: "`upstream-base` tag → commit `2a5eacd`. Unmoved." `git rev-parse upstream-base` prints `a158d18`, which is the annotated tag *object*; it dereferences to commit `2a5eacd`. Leave that line alone.

Rewrite the stale rows against the code. Keep the file's existing shape — a factual index, with reflection living in its journal — rather than converting it into a second CLAUDE.md.

- [ ] **Step 4: A tracked `AGENTS.md` at the root**

The spec calls for `.agents/AGENTS.md` symlinked to `.claude/CLAUDE.md`. Both paths are in `.gitignore`, so neither reaches a clone, and `.claude/CLAUDE.md` no longer exists. Create `AGENTS.md` at the repository root instead — the cross-tool convention several agents read — containing a short pointer rather than a copy:

```markdown
# AGENTS.md

This repository's agent-facing conventions live in [`CLAUDE.md`](CLAUDE.md) at
the repository root: commands, the three-layer architecture, the invariants a
new tool must preserve, and the two testing traps that will otherwise cost you
an afternoon.

Read that file before changing code here. It is kept true against the source;
if you find a claim in it that the code contradicts, the claim is the bug.
```

**A pointer, not a copy.** Two files with the same content drift, and this task exists because things drifted.

- [ ] **Step 5: Reconcile `CLAUDE.md` with the cull**

Task 2 deleted the paragraph about the three dead root scripts. Check the rest of `CLAUDE.md` against the tree again — Task 1 added a lint gate it does not mention, and Task 2 removed `TESTING.md`, which its "Related files" section may name.

- [ ] **Step 6: Commit**

```bash
rtk proxy git add -A
rtk proxy git status --porcelain
rtk proxy git commit -m "docs: make every agent-facing surface true against the code"
```

`.serena/` and `.cursor/skills/` have different ignore rules — `.serena/` is ignored entirely, `.cursor/skills/printful-mcp/` is explicitly un-ignored. Paste `status --porcelain` so it is visible which of your edits actually ship.

---

### Task 9: README and QUICKSTART

**Files:**
- Rewrite: `README.md` (731 lines)
- Rewrite: `QUICKSTART.md` (115 lines)

**Interfaces:**
- Consumes: Task 8's corrected tool list.
- Produces: the install instructions Task 10's manifests must agree with.

The README is the first thing anyone sees, and this fork exists because the upstream one was the first search result for a server that did not work. It currently claims 17 tools, documents an auto-retry on 429 that the code does not do, and points at scripts Task 2 deleted.

- [ ] **Step 1: Inventory what is false before writing anything**

```bash
rtk proxy git grep -n "17 tools\|19 tools\|auto-retry\|retry on 429\|test_server\.py\|test_comprehensive\|test_complete\|run-tests\|examples\.py\|TESTING\.md" -- README.md QUICKSTART.md
```

Paste the list. Every hit is a claim to fix or a reference to remove, and the list is the task's own definition of done.

- [ ] **Step 2: Rewrite `README.md`**

Keep: the upstream attribution, the LICENSE reference, the Printful referral context, and the tone — this is a fork of someone's project and the README says so.

Fix, at minimum:
- **The tool count.** 32, and say it is enforced by a test rather than maintained by hand, so the next person to add one does not have to remember to edit prose.
- **The 429 claim.** The client does **not** retry. It reads `Retry-After` into the error and gives up, deliberately, because a silent retry walks a user into Printful's 60-second mockup lockout.
- **Installation.** Task 10 ships a plugin marketplace and a `uvx`-based `.mcp.json`; the README's install section must match what those actually do. Write this section *after* Task 10 if the two disagree, and say so rather than documenting an intention.
- **Testing.** Point at `pytest`, and carry the two traps: `.venv/bin/python -m pytest` rather than a bare `pytest`, and `.env` needing to be moved aside rather than the variable unset.
- **The CLI.** The repository ships two surfaces now. The README currently describes one.

Use the elements-of-style skill if it is available. 731 lines of emoji headings is not a constraint to preserve; being accurate is.

- [ ] **Step 3: Rewrite `QUICKSTART.md`**

One path, working, in as few steps as possible: get a key, install, verify. If the plugin install from Task 10 is genuinely one command, this file gets much shorter.

- [ ] **Step 4: Run every command you wrote**

Every install command, every test command, every example invocation. **Paste the real output into your report.** A document of untested examples is how `TESTING.md` reached the state that got it deleted, and how the README came to promise a retry that does not exist.

Do not run anything that charges the account or creates an order.

- [ ] **Step 5: Commit**

```bash
rtk proxy git add README.md QUICKSTART.md
rtk proxy git commit -m "docs: rewrite the README and QUICKSTART against what the code does"
```

---

### Task 10: Distribution — the repository serves itself

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- Create: `.mcp.json`
- Create: `skills/printful-mcp/skill.json`, `skills/printful-cli/skill.json`
- Create: `skills/printful-mcp/SKILL.md`, `skills/printful-cli/SKILL.md` **as symlinks**
- Create: `.codex-plugin/plugin.json`, `.codex-plugin/INSTALL.md`
- Create: `scripts/bump-version.sh`
- Modify: `.gitignore` if any new path is caught by an existing rule

**Interfaces:**
- Consumes: Task 9's install instructions.
- Produces: the manifests Task 11's `manifests` CI job validates.

Modeled on `arscontexta`: the repository is simultaneously a plugin and the marketplace that serves it, so installation is one command.

- [ ] **Step 1: Check nothing you are about to create is gitignored**

```bash
for p in .claude-plugin .mcp.json skills .codex-plugin scripts; do
  printf '%-16s %s\n' "$p" "$(rtk proxy git check-ignore -q "$p" && echo IGNORED || echo ok)"
done
```

`.gitignore` already excludes `.agent/`, `.agents/`, `.claude/`, `.gemini/` and most of `.cursor/`. **A manifest that is gitignored ships to nobody**, which is exactly how the agent contract stayed invisible for two plans. If any path comes back IGNORED, un-ignore it explicitly with a `!` rule and say so in your report.

- [ ] **Step 2: The skill files are symlinks, not copies**

The real `SKILL.md` files already exist and Task 8 just corrected them:
- `.cursor/skills/printful-mcp/SKILL.md` — where the upstream author put it
- `src/printful_cli/skills/SKILL.md`

```bash
mkdir -p skills/printful-mcp skills/printful-cli
ln -s ../../.cursor/skills/printful-mcp/SKILL.md skills/printful-mcp/SKILL.md
ln -s ../../src/printful_cli/skills/SKILL.md skills/printful-cli/SKILL.md
rtk proxy git add skills/
```

**Copies drift.** Two files with the same content and no check between them is how this repository got a README claiming 17 tools while the code had 19. Git tracks symlinks; Task 11's `manifests` job asserts both resolve.

- [ ] **Step 3: `.mcp.json` — zero-install via uvx**

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

`printful-mcp` is a real console script — `pyproject.toml:89` declares it as `printful_mcp.server:main`, and that target resolves (verified: `printful_mcp.server.main` is callable). **Verify the whole path before committing it:**

```bash
uvx --from . printful-mcp --help
```

The `@dev` ref is correct **today**, because PR #1 is open and unmerged. It becomes `@main` when that PR lands. Note this in your report as a follow-up that a human must make, and do not pre-emptively point it at a branch that does not yet contain the code.

- [ ] **Step 4: The plugin and marketplace manifests**

`.claude-plugin/plugin.json`:

```json
{
  "name": "printful-mcp",
  "version": "0.1.0",
  "description": "Printful API for agents: an MCP server with 32 tools and a CLI, on one shared core.",
  "author": "Courtney Andrew Richardson",
  "license": "MIT",
  "keywords": ["printful", "print-on-demand", "mcp", "ecommerce", "fulfillment"],
  "mcpServers": "./.mcp.json",
  "skills": ["./skills/printful-mcp", "./skills/printful-cli"]
}
```

`.claude-plugin/marketplace.json`:

```json
{
  "name": "printful-mcp",
  "owner": { "name": "Courtney Andrew Richardson" },
  "plugins": [
    { "name": "printful-mcp", "source": "./", "description": "Printful API for agents." }
  ]
}
```

Check `license` against the actual `LICENSE` file rather than copying the string above — this is a fork, `LICENSE` stays unchanged, and stating the wrong one is a legal claim rather than a typo.

- [ ] **Step 5: `skill.json` for each skill, and the Codex manifest**

```json
{
  "name": "printful-mcp",
  "version": "0.1.0",
  "description": "Use the Printful MCP server's 32 tools: catalog, orders, mockups, shipping, files, stores, sync."
}
```

`.codex-plugin/plugin.json` carries the same name, version and description plus whatever interface block Codex requires; `.codex-plugin/INSTALL.md` is the install path for that surface. **If you cannot verify Codex's manifest schema from a source you can cite, say so and write the file to the closest documented shape rather than inventing fields** — an invented schema that validates locally and fails for a user is worse than an honest note.

- [ ] **Step 6: `scripts/bump-version.sh`**

The version now appears in six files: `pyproject.toml`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, and two `skill.json`. Six hand-edited copies of one number is a guaranteed drift.

```bash
#!/usr/bin/env bash
# Write one version into every manifest that carries it.
# Usage: scripts/bump-version.sh 0.2.0
set -euo pipefail

VERSION="${1:?usage: bump-version.sh <version>}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not semver: $VERSION" >&2; exit 1; }

python - "$VERSION" <<'PY'
import json, pathlib, re, sys

version = sys.argv[1]

pyproject = pathlib.Path("pyproject.toml")
text = pyproject.read_text()
new, n = re.subn(r'^version = ".*"$', f'version = "{version}"', text, count=1, flags=re.M)
if n != 1:
    sys.exit("pyproject.toml: expected exactly one version line, found %d" % n)
pyproject.write_text(new)

for path in [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
             ".codex-plugin/plugin.json",
             "skills/printful-mcp/skill.json", "skills/printful-cli/skill.json"]:
    p = pathlib.Path(path)
    if not p.exists():
        continue
    data = json.loads(p.read_text())
    if "version" in data:
        data["version"] = version
    for plugin in data.get("plugins", []):
        plugin["version"] = version
    p.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  {p}")

print(f"version -> {version}")
PY
```

`chmod +x scripts/bump-version.sh`. **Run it with the current version as a no-op and confirm `git diff` is empty** except for JSON reformatting you accept — a bump script whose first run produces a surprise diff is one nobody will trust enough to use.

- [ ] **Step 7: Verify every manifest parses and every referenced path exists**

```bash
.venv/bin/python - <<'PY'
import json, pathlib
ok = True
for p in pathlib.Path(".").glob("**/*.json"):
    if any(part in {".venv", "build", "node_modules", ".git"} for part in p.parts):
        continue
    try:
        json.loads(p.read_text())
    except Exception as e:
        ok = False
        print(f"INVALID {p}: {e}")
print("all manifests parse" if ok else "FIX THE ABOVE")
PY
for link in skills/printful-mcp/SKILL.md skills/printful-cli/SKILL.md; do
  printf '%-34s -> %s\n' "$link" "$(test -e "$link" && echo resolves || echo BROKEN)"
done
```

- [ ] **Step 8: Commit**

```bash
rtk proxy git add -A
rtk proxy git status --porcelain
rtk proxy git commit -m "feat: ship the repository as its own plugin marketplace"
```

---

### Task 11: CI and pre-commit

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: Tasks 1, 10 — the lint gate and the manifests.

This repository shipped broken for the entire life of `mcp` 2.x and nobody knew until a user hit it. The `server-boots` job exists to catch that class of break on the day it appears.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

Five jobs, from the spec:

```yaml
name: CI

on:
  push:
  pull_request:
  schedule:
    - cron: "0 6 * * 1"   # Monday 06:00 UTC, for the weekly jobs

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check src/
      - run: ruff format --check src/
      # No credentials, and none needed: the offline suite must pass without
      # them. That is also what makes this job work on a fork's pull request.
      - run: pytest -q

  server-boots:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      # The parity suite, not a hardcoded count: it asserts every core builder
      # is reachable through exactly one tool, and names the offending symbol
      # when it is not. A legitimate new tool must not fail CI for being new.
      - run: pytest -q src/printful_mcp/tests/test_server.py

  manifests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Every manifest parses, versions agree, referenced paths exist
        run: python scripts/check_manifests.py

  upstream-drift:
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      # Install the newest mcp WITHOUT the pin and report whether the server
      # still imports. Announces when a 2.x migration becomes worthwhile,
      # instead of discovering it through a user's bug report.
      - run: pip install -e . && pip install --upgrade "mcp"
      - run: python -c "import printful_mcp.server; print('imports clean')"

  live:
    if: github.event_name == 'schedule' && github.repository == 'crichalchemist/printful-mcp'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: pytest -m live -q
        env:
          PRINTFUL_API_KEY: ${{ secrets.PRINTFUL_API_KEY }}
          PRINTFUL_STORE_ID: ${{ secrets.PRINTFUL_STORE_ID }}
```

**The `live` job's repository guard is not decoration.** Without it a fork's scheduled run finds no secret, `Credentials.resolve()` fails loudly by design, and every fork gets a red CI badge for a job that was never theirs to run. `PRINTFUL_E2E_MOCKUPS` is deliberately absent, so mockup creation stays skipped.

- [ ] **Step 2: Write `scripts/check_manifests.py`**

The `manifests` job calls it; it must exist. Three assertions:

```python
#!/usr/bin/env python3
"""Every manifest parses, every version agrees, every referenced path exists."""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFESTS = [
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".codex-plugin/plugin.json",
    "skills/printful-mcp/skill.json",
    "skills/printful-cli/skill.json",
    ".mcp.json",
]

failures = []

pyproject = (ROOT / "pyproject.toml").read_text()
match = re.search(r'^version = "(.*)"$', pyproject, re.M)
if not match:
    sys.exit("pyproject.toml has no version line")
expected = match.group(1)

for name in MANIFESTS:
    path = ROOT / name
    if not path.exists():
        failures.append(f"{name}: missing")
        continue
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        failures.append(f"{name}: invalid JSON -- {e}")
        continue

    found = data.get("version")
    if found is not None and found != expected:
        failures.append(f"{name}: version {found!r}, pyproject says {expected!r}")

    # Every relative path a manifest names must resolve, or the plugin
    # installs and then fails for the user rather than for us.
    for value in json.dumps(data).split('"'):
        if value.startswith("./"):
            target = ROOT / value[2:]
            if not target.exists():
                failures.append(f"{name}: references {value}, which does not exist")

for link in ["skills/printful-mcp/SKILL.md", "skills/printful-cli/SKILL.md"]:
    if not (ROOT / link).exists():
        failures.append(f"{link}: broken symlink")

if failures:
    print("\n".join(failures))
    sys.exit(1)
print(f"manifests ok, version {expected}")
```

Run it locally and paste the output. Then **break one thing deliberately** — mismatch a version, point a manifest at a path that does not exist — confirm it exits non-zero naming that thing, and restore. A validator nobody has seen fail is a validator nobody should trust.

- [ ] **Step 3: `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.7
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: manifests
        name: manifests parse and versions agree
        entry: python scripts/check_manifests.py
        language: system
        pass_filenames: false
```

Pin `rev` to the ruff version Task 1 actually installed, not to the one written above — check it with `ruff --version` and use what you find.

- [ ] **Step 4: Prove the workflow is valid before pushing it**

A YAML file that parses is not a workflow that runs, but a workflow that does not parse never runs at all:

```bash
.venv/bin/python -c "
import yaml, pathlib
wf = yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())
print('jobs:', sorted(wf['jobs']))
"
```

Expect five job names. You cannot execute GitHub Actions locally here, so **say plainly in your report that the workflow is unverified end-to-end** and what would verify it — the first push to a branch with the workflow on it. Do not claim a job passes because its YAML is well-formed.

- [ ] **Step 5: Run every gate the workflow runs, locally**

```bash
.venv/bin/python -m ruff check src/
.venv/bin/python -m ruff format --check src/
find src -name '__pycache__' -type d -print0 | xargs -0 rm -rf
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
.venv/bin/python -m pytest -q src/printful_mcp/tests/test_server.py
.venv/bin/python scripts/check_manifests.py
```

Every one of those is a CI job's command. If one fails here it will fail there, and finding that out from a red badge on a public fork is the expensive way.

- [ ] **Step 6: Commit**

```bash
rtk proxy git add .github/ .pre-commit-config.yaml scripts/
rtk proxy git commit -m "ci: test, boot, manifest, drift and live jobs"
```

---

## Self-Review

**1. Spec coverage.** § The cull → Task 2, with the four already-done rows named so nobody re-deletes them. § Testing → Tasks 3–7. § Distribution → Task 10. § Continuous integration → Task 11. § Implementation phases 5 and 6 → the whole plan. Two spec statements are overridden with reasons recorded above rather than silently ignored: the `.agents/`/`.gemini/` symlinks, and the `server-boots` hardcoded count.

**2. Placeholder scan.** Two steps end in a judgment the implementer must make and report rather than a command that passes or fails: Task 7 Step 4 (whether `create_estimation_task` validates placements, which changes CLI behavior) and Task 10 Step 5 (the Codex manifest schema, which the plan explicitly refuses to invent). Both say what to report. Every other code step carries its code.

**3. Type consistency.** `toolsamples.py` is created in Task 6 Step 1 and consumed by Task 7 Step 2 under the same name. `TOOL_MODULES` is derived in Task 7 Step 2 and used by `test_server.py` and `toolsamples.py`, which is why Task 6 must land first. `scripts/check_manifests.py` is written in Task 11 Step 2 and called by the `manifests` job in Step 1 — the job is written before the script in the document, so Step 2 is not optional.

**4. Numbers.** Every figure in this plan was measured at `a4327ee`, not recalled: 447 default ruff findings and 52 under the installed config, 114 format-diff lines, 30 `format="json"` branches against 5 tests that use one, 216 of 279 surviving key mutations, 13 undocumented tools, 26 renderers. Where a task expects a number, it says to report the observed one and flag a difference rather than assume the plan is right.
