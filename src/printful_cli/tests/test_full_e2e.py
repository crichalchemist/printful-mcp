"""End-to-end tests for printful_cli against the LIVE Printful API.

These require a real PRINTFUL_API_KEY. Per HARNESS.md there is no graceful
degradation: without credentials these tests FAIL rather than skip, because a
harness that never touched the real backend would be proving nothing.

Two categories are deliberately excluded from the live path and are covered by
mocked unit tests in test_core.py instead:

  * `orders confirm` — submits to production and CHARGES the account.
  * `mockup create`  — 2 req/60s on new stores, 60s lockout, 20k files/24h cap.
                       Opt in with PRINTFUL_E2E_MOCKUPS=1.

See TEST.md for the full reasoning.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
from typing import ClassVar

import pytest

from printful_cli.core import catalog as catalog_mod
from printful_cli.core import orders as orders_mod
from printful_cli.core import shipping as shipping_mod
from printful_cli.core import stores as stores_mod
from printful_core.auth import Credentials
from printful_core.errors import PrintfulError
from printful_core.transport import SyncTransport

MOCKUPS_ENABLED = os.environ.get("PRINTFUL_E2E_MOCKUPS", "").strip() == "1"

# A stable, long-lived catalog product (Unisex Staple T-Shirt). Used for
# read-only lookups only.
KNOWN_PRODUCT_ID = 71

# Printful rejects a catalog order item with no `placements` — it has nothing
# to print. Verified live: "Property `placements` is required".
ARTWORK_URL = "https://raw.githubusercontent.com/github/explore/main/topics/python/python.png"


def _catalog_item(variant_id, quantity=1, with_design=True):
    """Build an order item in the shape the live v2 API accepts."""
    item = {"source": "catalog", "catalog_variant_id": variant_id, "quantity": quantity}
    if with_design:
        item["placements"] = [
            {
                "placement": "front",
                "technique": "dtg",
                "layers": [{"type": "file", "url": ARTWORK_URL}],
            }
        ]
    return item


def _resolve_cli(name):
    """Resolve installed CLI command; falls back to python -m for dev.

    Set env PRINTFUL_FORCE_INSTALLED=1 to require the installed command.
    """
    import shutil

    force = os.environ.get("PRINTFUL_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    # Hardcoded on purpose: the command is `printful` while the package keeps
    # its `_cli` suffix, so no derivation from `name` produces the right module.
    module = "printful_cli.printful_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


def _require_credentials():
    if not os.environ.get("PRINTFUL_API_KEY"):
        raise AssertionError(
            "PRINTFUL_API_KEY is not set.\n"
            "These E2E tests exercise the real Printful API and cannot run without "
            "credentials. This is a hard failure by design — see TEST.md.\n"
            "  export PRINTFUL_API_KEY=your-token\n"
            "Get a token at https://www.printful.com/dashboard/api"
        )


@pytest.fixture(scope="module")
def transport():
    _require_credentials()
    client = SyncTransport(Credentials.resolve())
    yield client
    client.close()


@pytest.fixture(scope="module")
def known_variant_id(transport):
    """Discover a real variant ID rather than hardcoding one."""
    summary = catalog_mod.list_variants(transport, KNOWN_PRODUCT_ID, limit=1)
    assert summary["variants"], "Expected at least one variant for product 71"
    return summary["variants"][0]["id"]


# --------------------------------------------------------------------------
# Read-only live calls — free and idempotent
# --------------------------------------------------------------------------


@pytest.mark.live
class TestLiveReadOnly:
    def test_countries_includes_us(self, transport):
        """The full country set must be returned, not just the first page.

        /v2/countries paginates at 20 by default and 'US' is not in the first
        page alphabetically — a single-request implementation reports that
        Printful does not ship to the United States.

        The returned-equals-total cross-check now lives in
        printful_core/tests/test_pagination.py::test_walks_every_page; the
        summarized shape carries no paging block to compare against.
        """
        summary = shipping_mod.list_countries(transport)
        codes = {c["code"] for c in summary["countries"]}
        assert summary["count"] > 20, "Looks like only the first page was fetched"
        for expected in ("US", "GB", "DE", "CA"):
            assert expected in codes, f"{expected} missing from country list"
        print(f"\n  Countries: {summary['count']}")

    def test_catalog_products_limit_respected(self, transport):
        summary = catalog_mod.list_products(transport, limit=3)
        assert summary["count"] == 3
        for product in summary["products"]:
            assert isinstance(product["id"], int)
            assert product["name"]
        print(f"\n  Products: {[p['id'] for p in summary['products']]}")

    def test_get_known_product(self, transport):
        data = catalog_mod.get_product(transport, KNOWN_PRODUCT_ID)
        body = data.get("data", data)
        assert body["id"] == KNOWN_PRODUCT_ID
        assert body.get("name")
        print(f"\n  Product {KNOWN_PRODUCT_ID}: {body.get('name')}")

    def test_variants_carry_size_and_color(self, transport):
        summary = catalog_mod.list_variants(transport, KNOWN_PRODUCT_ID, limit=5)
        assert summary["count"] > 0
        assert any(v["size"] for v in summary["variants"])
        assert any(v["color"] for v in summary["variants"])

    def test_variant_prices(self, transport, known_variant_id):
        data = catalog_mod.get_variant_prices(transport, known_variant_id)
        body = data.get("data", data)
        assert body, f"No pricing returned for variant {known_variant_id}"
        print(f"\n  Variant {known_variant_id} pricing keys: {list(body)[:5]}")

    def test_categories(self, transport):
        data = catalog_mod.list_categories(transport, limit=5)
        rows = data.get("data", []) or []
        assert rows
        assert all("id" in c for c in rows)

    def test_size_guide(self, transport):
        data = catalog_mod.get_size_guide(transport, KNOWN_PRODUCT_ID)
        body = data.get("data", data)
        assert body, "Expected size guide tables"

    def test_availability(self, transport):
        data = catalog_mod.get_availability(transport, KNOWN_PRODUCT_ID)
        assert data.get("data") is not None

    def test_store_list(self, transport):
        summary = stores_mod.list_stores(transport)
        print(f"\n  Stores: {[(s['id'], s['name']) for s in summary['stores']]}")
        assert summary["count"] >= 0

    def test_orders_list_succeeds(self, transport):
        summary = orders_mod.list_orders(transport, limit=3)
        assert summary["count"] >= 0

    def test_bad_product_id_errors_cleanly(self, transport):
        """A 404 must surface the API's real message, not a generic placeholder.

        Asserting only that a message exists is too weak: it passed while the
        error normalizer was silently reducing every v2 error to "Unknown error".
        """
        with pytest.raises(PrintfulError) as exc:
            catalog_mod.get_product(transport, 99999999)
        assert exc.value.status_code in (400, 404)
        assert exc.value.message != "Unknown error"
        assert "99999999" in exc.value.message, (
            f"Expected the API's own message, got {exc.value.message!r}"
        )
        print(f"\n  404 surfaced as: {exc.value.message}")


# --------------------------------------------------------------------------
# Live writes — drafts only, cleaned up afterwards
# --------------------------------------------------------------------------


@pytest.mark.live
class TestLiveDraftOrder:
    def test_shipping_rates_for_us_destination(self, transport, known_variant_id):
        recipient = {
            "name": "CLI Harness Test",
            "address1": "11025 Westlake Dr",
            "city": "Charlotte",
            "state_code": "NC",
            "country_code": "US",
            "zip": "28273",
        }
        # Rates can be quoted before artwork exists — no placements here,
        # deliberately, to prove that asymmetry against the live API.
        items = [_catalog_item(known_variant_id, with_design=False)]
        summary = shipping_mod.calculate_rates(transport, recipient, items)
        assert summary["count"] > 0, "Expected at least one shipping rate"
        first = summary["rates"][0]
        # The live payload names these `shipping` / `shipping_method_name`;
        # a summarizer reading `id`/`name` would leave both None.
        assert first["id"], f"Rate has no method code: {first}"
        assert first["name"], f"Rate has no method name: {first}"
        assert first["rate"], f"Rate has no price: {first}"
        print(f"\n  Rates: {[(r['name'], r['rate'], r['currency']) for r in summary['rates']]}")

    def test_create_and_cancel_draft_order(self, transport, known_variant_id):
        """Create a real DRAFT order, verify it, then clean it up.

        Drafts are not charged. The order is cancelled at the end so the suite
        leaves no residue in the user's account.
        """
        recipient = {
            "name": "CLI Harness Test",
            "address1": "11025 Westlake Dr",
            "city": "Charlotte",
            "state_code": "NC",
            "country_code": "US",
            "zip": "28273",
        }
        created = orders_mod.create_order(transport, recipient, [_catalog_item(known_variant_id)])
        body = created.get("data", created)
        order_id = body.get("id")
        assert order_id, f"No order ID in response: {body}"
        assert body.get("status") == "draft", (
            f"Expected a draft order, got status={body.get('status')!r}. "
            "Refusing to continue — a non-draft order may be billable."
        )
        print(f"\n  Draft order created: {order_id}")

        try:
            fetched = orders_mod.get_order(transport, str(order_id))
            assert fetched.get("data", fetched).get("id") == order_id

            items = orders_mod.list_items(transport, str(order_id))
            assert items.get("data") is not None
        finally:
            # Cancelling a DRAFT is free and non-destructive.
            orders_mod.cancel_order(transport, str(order_id))
            print(f"  Draft order {order_id} cancelled (cleanup)")

    ESTIMATE_RECIPIENT: ClassVar[dict] = {
        "address1": "11025 Westlake Dr",
        "city": "Charlotte",
        "state_code": "NC",
        "country_code": "US",
        "zip": "28273",
    }

    def test_estimate_costs(self, transport, known_variant_id):
        data = orders_mod.estimate_costs(
            transport,
            self.ESTIMATE_RECIPIENT,
            [_catalog_item(known_variant_id)],
            max_wait=45,
            interval=3,
        )
        body = data.get("data", data)
        assert body.get("status") == "completed"
        assert body.get("costs"), "Completed estimate should carry costs"
        print(f"\n  Estimated total: {body['costs'].get('total')} {body['costs'].get('currency')}")

    def test_estimation_rejects_an_item_with_no_artwork(self, transport, known_variant_id):
        """Where the artwork asymmetry ends: estimation sides with ordering.

        Shipping rates quote an item with no `placements`; `POST /v2/orders`
        rejects one. `POST /v2/order-estimation-tasks` was unestablished until
        this test asked it live: it rejects, with the same message the order
        endpoint gives, and it rejects on the initial POST rather than by
        completing a task with a failure. Estimation is free and places no
        order, so this costs nothing to assert.

        The placements assertion alone cannot support that second clause: a
        task that was created and then failed for the same reason would also
        carry "placements" in its message. The prefix assertion below is what
        tells the two paths apart.
        """
        with pytest.raises(PrintfulError) as exc:
            orders_mod.estimate_costs(
                transport,
                self.ESTIMATE_RECIPIENT,
                [_catalog_item(known_variant_id, with_design=False)],
                max_wait=45,
                interval=3,
            )
        assert "placements" in exc.value.message, (
            f"Expected the API's own placements message, got {exc.value.message!r}"
        )
        # Which path rejected. polling._estimation_failure builds its message as
        # "Order estimation failed: " + the task's failure_reasons; an initial-POST
        # rejection carries the API's message verbatim through errors.extract_message
        # with no prefix. Both contain "placements", so only the prefix separates them.
        assert not exc.value.message.startswith("Order estimation failed: "), (
            "The estimate was REJECTED BY A POLLED TASK FAILURE, not by the initial "
            "POST: the message carries polling._estimation_failure's prefix. The API "
            "therefore accepts the request and fails the task afterwards, so this "
            "test's docstring claim -- that it rejects on the initial POST -- is "
            f"false and should be deleted rather than reworded. Got: {exc.value.message!r}"
        )
        print(f"\n  Estimate without artwork refused on the initial POST: {exc.value.message}")


# --------------------------------------------------------------------------
# Opt-in: writes to the file library and burns mockup quota
# --------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(
    not MOCKUPS_ENABLED,
    reason="Mockup/file E2E is opt-in: rate limited (2/60s on new stores) and "
    "consumes the account's 20k files/24h budget. Set PRINTFUL_E2E_MOCKUPS=1.",
)
class TestLiveMockups:
    DESIGN_URL = "https://raw.githubusercontent.com/github/explore/main/topics/python/python.png"

    def test_mockup_styles(self, transport):
        from printful_cli.core import mockups as mockups_mod

        data = mockups_mod.list_styles(transport, KNOWN_PRODUCT_ID)
        assert data.get("data") is not None

    def test_create_mockup_and_fetch_image(self, transport, known_variant_id):
        """Create a real mockup and verify the returned URL serves image bytes."""
        # httpx, not requests: the CLI carries one HTTP stack, and it is the
        # one printful_core uses. Redirects are not followed by default here.
        import httpx

        from printful_cli.core import mockups as mockups_mod

        created = mockups_mod.create_task(
            transport, KNOWN_PRODUCT_ID, [known_variant_id], self.DESIGN_URL
        )
        body = created.get("data", created)
        task_id = body.get("id")
        assert task_id

        done = mockups_mod.wait_for_task(transport, task_id, max_wait=180, interval=5)
        urls = mockups_mod.extract_mockup_urls(done)
        assert urls, "Completed mockup task returned no URLs"

        resp = httpx.get(urls[0], timeout=60, follow_redirects=True)
        assert resp.status_code == 200
        assert len(resp.content) > 1000, "Mockup image suspiciously small"
        # JPEG starts FF D8 FF; PNG starts \x89PNG
        assert resp.content[:3] == b"\xff\xd8\xff" or resp.content[:4] == b"\x89PNG", (
            "Mockup URL did not serve a real JPEG or PNG"
        )
        print(f"\n  Mockup: {urls[0]} ({len(resp.content):,} bytes)")

    def test_file_add_list_get_roundtrip(self, transport):
        from printful_cli.core import files as files_mod

        added = files_mod.add_file(transport, self.DESIGN_URL, filename="harness-test.png")
        body = added.get("data", added)
        file_id = body.get("id")
        assert file_id

        fetched = files_mod.get_file(transport, file_id)
        assert fetched.get("data", fetched).get("id") == file_id
        print(f"\n  File {file_id} round-tripped")


# --------------------------------------------------------------------------
# CLI subprocess tests — the installed command, as a user or agent runs it
# --------------------------------------------------------------------------


class TestCLISubprocess:
    CLI_BASE = _resolve_cli("printful")

    def _run(self, args, check=True, env=None):
        run_env = dict(os.environ)
        if env:
            run_env.update(env)
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
            env=run_env,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "catalog" in result.stdout

    def test_version(self):
        """The installed binary reports the version the project declares.

        Read from `pyproject.toml` rather than hardcoded. A literal here is how
        `printful_cli.__version__` drifted to 1.0.0 while `pyproject.toml` — what
        a `pip install` actually publishes — stayed at 0.1.0: this assertion was
        guarding the disagreement instead of catching it.
        """
        pyproject = pathlib.Path(__file__).resolve().parents[3] / "pyproject.toml"
        declared = re.search(r'^version = "(.*)"$', pyproject.read_text(), re.M)
        assert declared, f"no version line in {pyproject}"
        result = self._run(["--version"])
        assert result.returncode == 0
        assert declared.group(1) in result.stdout

    def test_confirm_without_yes_refuses(self, tmp_path):
        """The money guard must hold through the real installed binary."""
        result = self._run(
            ["--json", "--session", str(tmp_path / "s.json"), "orders", "confirm", "1"],
            check=False,
        )
        assert result.returncode != 0
        payload = json.loads(result.stdout or result.stderr)
        assert "without --yes" in payload["error"]

    def test_draft_workflow_persists_across_processes(self, tmp_path):
        session = str(tmp_path / "workflow.json")
        r1 = self._run(
            [
                "--json",
                "--session",
                session,
                "draft",
                "recipient",
                "--name",
                "Jane Doe",
                "--address1",
                "1 Main St",
                "--city",
                "Berlin",
                "--country-code",
                "DE",
                "--zip",
                "10115",
            ]
        )
        assert json.loads(r1.stdout)["recipient_set"] is True

        # A catalog item needs artwork before the order can be created, though
        # not before it can be rate-quoted.
        r2 = self._run(
            [
                "--json",
                "--session",
                session,
                "draft",
                "add-item",
                "--variant-id",
                "4012",
                "--quantity",
                "2",
            ]
        )
        summary = json.loads(r2.stdout)["summary"]
        assert summary["priceable"] is True
        assert summary["complete"] is False
        assert summary["items_without_design"] == 1

        r2b = self._run(
            [
                "--json",
                "--session",
                session,
                "draft",
                "add-item",
                "--variant-id",
                "4013",
                "--quantity",
                "1",
                "--image-url",
                ARTWORK_URL,
            ]
        )
        assert json.loads(r2b.stdout)["summary"]["items_without_design"] == 1

        r3 = self._run(["--json", "--session", session, "draft", "show"])
        draft = json.loads(r3.stdout)["draft"]
        assert draft["recipient"]["name"] == "Jane Doe"
        assert draft["items"][0]["quantity"] == 2

    @pytest.mark.live
    def test_json_countries(self):
        _require_credentials()
        result = self._run(["--json", "ship", "countries"])
        payload = json.loads(result.stdout)
        assert payload["count"] > 0

    @pytest.mark.live
    def test_json_catalog_products(self):
        _require_credentials()
        result = self._run(["--json", "catalog", "products", "--limit", "2"])
        payload = json.loads(result.stdout)
        assert len(payload["products"]) == 2
        print(f"\n  CLI returned products: {[p['id'] for p in payload['products']]}")

    @pytest.mark.live
    def test_test_command_reports_ok(self):
        _require_credentials()
        result = self._run(["--json", "test"])
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["countries_returned"] > 0

    def test_missing_credentials_fails_loudly(self, tmp_path):
        """With no token anywhere, the CLI must explain how to set one."""
        result = self._run(
            ["--json", "--session", str(tmp_path / "s.json"), "ship", "countries"],
            check=False,
            env={"PRINTFUL_API_KEY": "", "HOME": str(tmp_path)},
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "printful.com/dashboard/api" in combined
