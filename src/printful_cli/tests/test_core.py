"""Unit tests for printful_cli.

Synthetic data and a fake transport only — no network, no API key. The billable
endpoint (orders confirm) is asserted here against the fake transport precisely
because it must never be exercised live.

The HTTP layer, the request builders, the error envelopes, pagination and the
formatters now live in printful_core and are tested in src/printful_core/tests.
What is left here is what the CLI itself owns: session state, polling loops,
result shaping for the command layer, and the --yes guards.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from printful_core import auth as auth_mod
from printful_core.auth import CONFIG_FILE as CORE_CONFIG_FILE
from printful_core.errors import PrintfulError
from printful_cli.core import catalog as catalog_mod
from printful_cli.core import files as files_mod
from printful_cli.core import mockups as mockups_mod
from printful_cli.core import orders as orders_mod
from printful_cli.core import shipping as shipping_mod
from printful_cli.core import stores as stores_mod
from printful_cli.core.session import (
    DEFAULT_SESSION_FILE,
    DraftOrder,
    PrintfulSession,
    _locked_save_json,
)


# --------------------------------------------------------------------------
# Fake transport
# --------------------------------------------------------------------------

class FakeTransport:
    """Records the Requests it is handed and replays queued response bodies.

    A queued Exception is raised instead of returned, which is how the core's
    transport reports an API error to these modules.
    """

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.requests = []

    def send(self, request, extra_headers=None):
        self.requests.append(request)
        if not self.responses:
            return {"data": {}}
        body = self.responses.pop(0)
        if isinstance(body, Exception):
            raise body
        return body


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Keep tests off the developer's real env vars and config file."""
    monkeypatch.delenv("PRINTFUL_API_KEY", raising=False)
    monkeypatch.delenv("PRINTFUL_STORE_ID", raising=False)
    monkeypatch.setattr(auth_mod, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(auth_mod, "CONFIG_DIR", tmp_path)


# --------------------------------------------------------------------------
# DraftOrder
# --------------------------------------------------------------------------

class TestDraftOrder:
    def test_set_recipient_stores_known_fields(self):
        d = DraftOrder()
        d.set_recipient(name="Jane", city="Austin")
        assert d.recipient["name"] == "Jane"
        assert d.recipient["city"] == "Austin"

    def test_set_recipient_rejects_unknown_field(self):
        d = DraftOrder()
        with pytest.raises(ValueError, match="Unknown recipient field"):
            d.set_recipient(planet="Mars")

    def test_set_recipient_ignores_none(self):
        d = DraftOrder()
        d.set_recipient(name="Jane", city=None)
        assert "city" not in d.recipient

    def test_add_item_builds_catalog_item(self):
        d = DraftOrder()
        item = d.add_item(4012, 3)
        assert item == {"source": "catalog", "catalog_variant_id": 4012, "quantity": 3}
        assert len(d.items) == 1

    def test_add_item_rejects_zero_quantity(self):
        d = DraftOrder()
        with pytest.raises(ValueError, match="quantity must be >= 1"):
            d.add_item(4012, 0)

    def test_add_item_with_image_nests_placement(self):
        d = DraftOrder()
        item = d.add_item(4012, 1, placement="back", image_url="http://x/a.png",
                          technique="embroidery")
        placement = item["placements"][0]
        assert placement["placement"] == "back"
        assert placement["technique"] == "embroidery"
        assert placement["layers"][0]["url"] == "http://x/a.png"

    def test_add_item_image_defaults_front_dtg(self):
        d = DraftOrder()
        item = d.add_item(4012, 1, image_url="http://x/a.png")
        assert item["placements"][0]["placement"] == "front"
        assert item["placements"][0]["technique"] == "dtg"

    def test_remove_item_pops_by_index(self):
        d = DraftOrder()
        d.add_item(1, 1)
        d.add_item(2, 1)
        removed = d.remove_item(0)
        assert removed["catalog_variant_id"] == 1
        assert len(d.items) == 1

    def test_remove_item_empty_draft_raises(self):
        with pytest.raises(ValueError, match="no items"):
            DraftOrder().remove_item(0)

    def test_remove_item_out_of_range_names_valid_range(self):
        d = DraftOrder()
        d.add_item(1, 1)
        with pytest.raises(ValueError, match="valid indices 0-0"):
            d.remove_item(5)

    def test_missing_fields_lists_absent_recipient_fields(self):
        missing = DraftOrder().missing_fields()
        assert "recipient.name" in missing
        assert "recipient.address1" in missing
        assert "items (at least one)" in missing

    def test_state_code_required_for_us(self):
        d = DraftOrder()
        d.set_recipient(name="J", address1="1 St", city="Austin",
                        country_code="US", zip="78701")
        d.add_item(1, 1)
        assert "recipient.state_code" in d.missing_fields()

    @pytest.mark.parametrize("country", ["US", "CA", "AU"])
    def test_state_code_required_for_each_gated_country(self, country):
        d = DraftOrder()
        d.set_recipient(name="J", address1="1 St", city="X",
                        country_code=country, zip="1")
        d.add_item(1, 1)
        assert "recipient.state_code" in d.missing_fields()

    def test_state_code_not_required_elsewhere(self):
        d = DraftOrder()
        d.set_recipient(name="J", address1="1 St", city="Berlin",
                        country_code="DE", zip="10115")
        d.add_item(1, 1, image_url="http://x/a.png")
        assert d.missing_fields() == []
        assert d.is_complete()

    def test_to_api_payload_raises_while_incomplete(self):
        with pytest.raises(ValueError, match="incomplete"):
            DraftOrder().to_api_payload()

    def test_to_api_payload_shape(self):
        d = DraftOrder()
        d.set_recipient(name="J", address1="1 St", city="Berlin",
                        country_code="DE", zip="10115")
        d.add_item(4012, 2, image_url="http://x/a.png")
        payload = d.to_api_payload()
        assert payload["recipient"]["name"] == "J"
        assert payload["order_items"][0]["catalog_variant_id"] == 4012
        assert "external_id" not in payload

    # --- Regression: catalog order items require placements -------------
    # Verified live: "Property `placements` is required". Shipping rates do
    # NOT require them, so the draft stays priceable without artwork.

    def test_item_without_design_blocks_submission(self):
        d = DraftOrder()
        d.set_recipient(name="J", address1="1 St", city="Berlin",
                        country_code="DE", zip="10115")
        d.add_item(4012, 1)
        missing = d.missing_fields()
        assert any("placements" in m for m in missing)
        assert not d.is_complete()

    def test_missing_placements_message_is_actionable(self):
        d = DraftOrder()
        d.add_item(4012, 1)
        message = next(m for m in d.missing_fields() if "placements" in m)
        assert "4012" in message
        assert "--image-url" in message

    def test_item_with_design_is_complete(self):
        d = DraftOrder()
        d.set_recipient(name="J", address1="1 St", city="Berlin",
                        country_code="DE", zip="10115")
        d.add_item(4012, 1, image_url="http://x/a.png")
        assert d.missing_fields() == []
        assert d.is_complete()

    def test_priceable_without_artwork(self):
        """Rates can be quoted before a design exists."""
        d = DraftOrder()
        d.set_recipient(country_code="DE")
        d.add_item(4012, 1)
        assert d.priceable() is True
        assert d.is_complete() is False

    def test_not_priceable_without_country(self):
        d = DraftOrder()
        d.add_item(4012, 1)
        assert d.priceable() is False

    def test_summary_counts_items_without_design(self):
        d = DraftOrder()
        d.add_item(1, 1)
        d.add_item(2, 1, image_url="http://x/a.png")
        assert d.summary()["items_without_design"] == 1

    def test_non_catalog_source_exempt_from_placements(self):
        d = DraftOrder()
        d.set_recipient(name="J", address1="1 St", city="Berlin",
                        country_code="DE", zip="10115")
        d.add_item(4012, 1)
        d.items[0]["source"] = "sync_product"
        assert d.missing_fields() == []

    def test_to_api_payload_includes_optional_fields(self):
        d = DraftOrder()
        d.set_recipient(name="J", address1="1 St", city="Berlin",
                        country_code="DE", zip="10115")
        d.add_item(1, 1, image_url="http://x/a.png")
        d.external_id = "ext-1"
        d.shipping = "STANDARD"
        payload = d.to_api_payload()
        assert payload["external_id"] == "ext-1"
        assert payload["shipping"] == "STANDARD"

    def test_summary_counts_quantities(self):
        d = DraftOrder()
        d.add_item(1, 2)
        d.add_item(2, 3)
        s = d.summary()
        assert s["item_count"] == 2
        assert s["total_quantity"] == 5

    def test_clear_resets(self):
        d = DraftOrder()
        d.set_recipient(name="J")
        d.add_item(1, 1)
        d.clear()
        assert d.items == []
        assert d.recipient == {}


# --------------------------------------------------------------------------
# PrintfulSession
# --------------------------------------------------------------------------

class TestPrintfulSession:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "s.json")
        s = PrintfulSession(path)
        s.draft.set_recipient(name="Jane", country_code="DE")
        s.draft.add_item(4012, 2)
        s.set_store("999")
        s.record_file(5, "http://x/a.png", "a.png")
        s.save_history("catalog products", {"ok": True})
        s.save_session()

        reloaded = PrintfulSession(path)
        assert reloaded.draft.recipient["name"] == "Jane"
        assert reloaded.draft.items[0]["catalog_variant_id"] == 4012
        assert reloaded.store_id == "999"
        assert reloaded.files[0]["id"] == 5
        assert reloaded.history[0]["command"] == "catalog products"

    def test_record_file_marks_modified(self, tmp_path):
        s = PrintfulSession(str(tmp_path / "s.json"))
        assert s._modified is False
        s.record_file(1, "u", "f")
        assert s._modified is True

    def test_history_truncates_at_max(self, tmp_path):
        s = PrintfulSession(str(tmp_path / "s.json"))
        for i in range(60):
            s.save_history(f"cmd {i}")
        assert len(s.history) == 50
        assert s.history[-1]["command"] == "cmd 59"

    def test_clear_empties_everything(self, tmp_path):
        s = PrintfulSession(str(tmp_path / "s.json"))
        s.draft.add_item(1, 1)
        s.record_file(1, "u", "f")
        s.save_history("x")
        s.clear()
        assert s.draft.items == []
        assert s.files == []
        assert s.history == []

    def test_corrupt_session_loads_empty(self, tmp_path):
        path = tmp_path / "s.json"
        path.write_text("{not json")
        s = PrintfulSession(str(path))
        assert s.draft.items == []
        assert s.history == []

    def test_missing_session_file_is_fine(self, tmp_path):
        s = PrintfulSession(str(tmp_path / "nope" / "s.json"))
        assert s.draft.items == []

    def test_locked_save_creates_parent_dirs(self, tmp_path):
        target = str(tmp_path / "deep" / "nested" / "s.json")
        _locked_save_json(target, {"a": 1}, indent=2)
        assert json.loads(open(target).read()) == {"a": 1}

    def test_status_reports_session_file(self, tmp_path):
        path = str(tmp_path / "s.json")
        assert PrintfulSession(path).status()["session_file"] == path

    def test_session_lives_beside_the_config_in_config_printful(self):
        """Both halves: beside config.json, AND in ~/.config/printful.

        Asserting only the relationship to CONFIG_FILE would keep passing if
        the core's config directory itself moved somewhere else.
        """
        assert Path(DEFAULT_SESSION_FILE).parent == CORE_CONFIG_FILE.parent
        assert Path(DEFAULT_SESSION_FILE) == (
            Path.home() / ".config" / "printful" / "session.json"
        )

    def test_saved_session_is_not_world_readable(self, tmp_path):
        """It holds the recipient block: name, address, email, phone."""
        path = str(tmp_path / "s.json")
        session = PrintfulSession(path)
        session.draft.set_recipient(name="Jane", address1="1 St",
                                    email="jane@example.com", phone="555")
        session.save_session()
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------

_ITEM = {"source": "catalog", "catalog_variant_id": 4012, "quantity": 1,
         "placements": [{"placement": "front", "technique": "dtg",
                         "layers": [{"type": "file", "url": "http://x/a.png"}]}]}


class TestOrders:
    def test_confirm_targets_confirmation_endpoint(self):
        """The billable endpoint — asserted here so it is never called live."""
        t = FakeTransport([{"data": {"status": "pending"}}])
        orders_mod.confirm_order(t, "123")
        request = t.requests[0]
        assert request.method == "POST"
        assert request.path == "/orders/123/confirmation"
        assert request.version == "v2"

    def test_cancel_reports_cancelled_when_the_api_returns_no_body(self):
        t = FakeTransport([{}])
        result = orders_mod.cancel_order(t, "123")
        assert t.requests[0].method == "DELETE"
        assert result == {"order_id": "123", "status": "cancelled"}

    def test_create_sends_recipient_and_items_as_one_body(self):
        """The command layer holds them apart; the order body puts them together."""
        t = FakeTransport([{"data": {"id": 5}}])
        orders_mod.create_order(t, {"country_code": "DE"}, [_ITEM], "ext-1")
        request = t.requests[0]
        assert request.path == "/orders"
        assert request.json["recipient"] == {"country_code": "DE"}
        assert request.json["order_items"][0]["catalog_variant_id"] == 4012
        assert request.json["external_id"] == "ext-1"

    def test_estimate_polls_until_completed(self):
        t = FakeTransport([
            {"data": {"id": "t1", "status": "pending"}},
            {"data": {"id": "t1", "status": "pending"}},
            {"data": {"id": "t1", "status": "completed",
                      "costs": {"total": "25.00"}}},
        ])
        result = orders_mod.estimate_costs(t, {}, [_ITEM], interval=0, max_wait=5)
        assert result["data"]["status"] == "completed"

    def test_estimate_raises_on_failure_with_reasons(self):
        t = FakeTransport([
            {"data": {"id": "t1", "status": "pending"}},
            {"data": {"id": "t1", "status": "failed",
                      "failure_reasons": ["bad variant"]}},
        ])
        with pytest.raises(PrintfulError, match="bad variant"):
            orders_mod.estimate_costs(t, {}, [_ITEM], interval=0, max_wait=5)

    def test_estimate_timeout_names_task(self):
        t = FakeTransport([{"data": {"id": "t9", "status": "pending"}}
                           for _ in range(10)])
        with pytest.raises(PrintfulError, match="t9"):
            orders_mod.estimate_costs(t, {}, [_ITEM], interval=0, max_wait=0.01)

    def test_estimate_no_poll_returns_task(self):
        t = FakeTransport([{"data": {"id": "t1", "status": "pending"}}])
        result = orders_mod.estimate_costs(t, {}, [_ITEM], poll=False)
        assert result["data"]["id"] == "t1"
        assert len(t.requests) == 1


# --------------------------------------------------------------------------
# Mockups
# --------------------------------------------------------------------------

class TestMockups:
    def test_create_requires_variants(self):
        with pytest.raises(ValueError, match="variant ID"):
            mockups_mod.create_task(FakeTransport(), 71, [], "http://x/a.png")

    def test_create_requires_image(self):
        with pytest.raises(ValueError, match="image URL"):
            mockups_mod.create_task(FakeTransport(), 71, [1], "")

    def test_create_forwards_every_option_to_the_right_parameter(self):
        """The CLI forwards positionally across a parameter rename.

        `mockup_style_ids` here is `style_ids` in the core builder, and the
        placement/technique/format arguments sit between them. A slipped
        position binds silently and builds a valid-looking wrong request.
        """
        t = FakeTransport([{"data": {"id": "t1"}}])
        mockups_mod.create_task(t, 71, [4012], "http://x/a.png",
                                "back", "embroidery", [5], "png")
        body = t.requests[0].json
        product = body["products"][0]
        assert body["format"] == "png"
        assert product["catalog_product_id"] == 71
        assert product["catalog_variant_ids"] == [4012]
        assert product["mockup_style_ids"] == [5]
        assert product["placements"][0]["placement"] == "back"
        assert product["placements"][0]["technique"] == "embroidery"
        assert product["placements"][0]["layers"][0]["url"] == "http://x/a.png"

    def test_wait_raises_on_failed(self):
        t = FakeTransport([{"data": {"status": "failed", "reason": "bad file"}}])
        with pytest.raises(PrintfulError, match="bad file"):
            mockups_mod.wait_for_task(t, "t1", max_wait=5, interval=0)

    def test_wait_timeout_names_task(self):
        t = FakeTransport([{"data": {"status": "pending"}} for _ in range(5)])
        with pytest.raises(PrintfulError, match="t7"):
            mockups_mod.wait_for_task(t, "t7", max_wait=0.01, interval=0)

    def test_templates_ask_for_one_product_not_a_page(self):
        """printful_core.endpoints.stores.list_templates shares this name and
        takes (limit, offset) — a product ID there binds silently to limit."""
        t = FakeTransport([{"data": []}])
        mockups_mod.list_templates(t, 71)
        assert t.requests[0].path == "/catalog-products/71/mockup-templates"
        assert t.requests[0].params == {}


# --------------------------------------------------------------------------
# Shapes the command layer depends on
# --------------------------------------------------------------------------

class TestSummarizedReturns:
    """Listing operations summarize before returning.

    The command layer reads `summary["products"]`, `["count"]` and so on
    directly. Summarizing a second time at the call site would silently yield
    count 0 rather than raising, so the contract is pinned here.
    """

    def test_products(self):
        t = FakeTransport([{"data": [{"id": 1, "name": "Tee"}], "paging": {}}])
        out = catalog_mod.list_products(t, limit=1)
        assert out["count"] == 1
        assert out["products"][0]["name"] == "Tee"

    def test_variants(self):
        t = FakeTransport([{"data": [{"id": 4012, "size": "L", "color": "Black"}]}])
        out = catalog_mod.list_variants(t, 71)
        assert out["variants"][0]["size"] == "L"
        assert out["count"] == 1

    def test_orders(self):
        t = FakeTransport([{"data": [{"id": 1, "status": "draft"}]}])
        out = orders_mod.list_orders(t)
        assert out["orders"][0]["total"] is None
        assert out["count"] == 1

    def test_rates(self):
        t = FakeTransport([{"data": [{"shipping": "STANDARD",
                                      "shipping_method_name": "Flat Rate",
                                      "rate": "4.95"}]}])
        out = shipping_mod.calculate_rates(t, {"country_code": "US"}, [_ITEM])
        assert out["rates"][0]["id"] == "STANDARD"
        assert out["rates"][0]["name"] == "Flat Rate"
        assert out["count"] == 1

    def test_stores(self):
        t = FakeTransport([{"data": [{"id": 1, "name": "Alpha", "type": "native"}]}])
        out = stores_mod.list_stores(t)
        assert out["stores"][0]["name"] == "Alpha"
        assert out["count"] == 1


class TestCountriesPagination:
    """Regression: /v2/countries defaults to 20 of ~239 rows and omits 'US'.

    The bug was found live and fixed once. The CLI must keep reaching the
    country list through printful_core.pagination.collect_pages; swapping it
    for a bare transport.send would issue one request and drop the rest, which
    is what these two tests fail on.
    """

    def _pages(self):
        return [
            {"data": [{"code": "AF"}, {"code": "AL"}],
             "paging": {"total": 5, "limit": 2, "offset": 0}},
            {"data": [{"code": "DE"}, {"code": "GB"}],
             "paging": {"total": 5, "limit": 2, "offset": 2}},
            {"data": [{"code": "US"}],
             "paging": {"total": 5, "limit": 2, "offset": 4}},
        ]

    def test_every_page_is_requested(self):
        t = FakeTransport(self._pages())
        summary = shipping_mod.list_countries(t)
        assert [c["code"] for c in summary["countries"]] == [
            "AF", "AL", "DE", "GB", "US"
        ]
        assert len(t.requests) == 3

    def test_us_present_after_pagination(self):
        t = FakeTransport(self._pages())
        summary = shipping_mod.list_countries(t)
        assert "US" in {c["code"] for c in summary["countries"]}
        assert summary["count"] == 5


class TestShipping:
    def test_tax_targets_v1(self):
        t = FakeTransport([{"rate": 0.08}])
        shipping_mod.calculate_tax(t, "US", "CA", "LA", "90001")
        request = t.requests[0]
        assert request.version == "v1"
        assert request.path == "/tax/rates"
        assert request.json["recipient"]["state_code"] == "CA"


class TestFiles:
    def test_add_requires_url(self):
        with pytest.raises(ValueError, match="URL is required"):
            files_mod.add_file(FakeTransport(), "")

    def test_list_added_is_labelled_session_local(self):
        out = files_mod.list_added([{"id": 1, "filename": "a.png"}])
        assert out["source"] == "session-local"
        assert "no list-files endpoint" in out["note"]
        assert out["count"] == 1

    def test_list_added_empty(self):
        assert files_mod.list_added([])["count"] == 0


# --------------------------------------------------------------------------
# CLI guards (no network)
# --------------------------------------------------------------------------

def _session_path(tmp_path, name="s.json"):
    return str(tmp_path / name)


def _fresh_cli():
    """Import the CLI module with its globals reset between tests."""
    from printful_cli import printful_cli

    printful_cli._session = None
    printful_cli._transport = None
    printful_cli._repl_mode = False
    return printful_cli


class TestCLIGuards:
    def test_confirm_without_yes_exits_nonzero(self, tmp_path):
        cli_mod = _fresh_cli()
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--session", _session_path(tmp_path), "orders", "confirm", "123"],
            obj={},
        )
        assert result.exit_code != 0
        assert "without --yes" in result.output

    def test_confirm_refusal_mentions_charging(self, tmp_path):
        cli_mod = _fresh_cli()
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--session", _session_path(tmp_path), "orders", "confirm", "123"],
            obj={},
        )
        assert "CHARGES" in result.output

    def test_cancel_without_yes_exits_nonzero(self, tmp_path):
        cli_mod = _fresh_cli()
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--session", _session_path(tmp_path), "orders", "cancel", "123"],
            obj={},
        )
        assert result.exit_code != 0
        assert "without --yes" in result.output

    def test_dry_run_confirm_makes_no_call(self, tmp_path):
        cli_mod = _fresh_cli()
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--json", "--dry-run", "--session", _session_path(tmp_path),
             "orders", "confirm", "123", "--yes"],
            obj={},
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["dry_run"] is True
        assert payload["would_post"] == "/v2/orders/123/confirmation"
        # No backend was ever constructed, so no credentials were needed.
        assert cli_mod._transport is None

    def test_json_error_output_is_parseable(self, tmp_path):
        cli_mod = _fresh_cli()
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--json", "--session", _session_path(tmp_path),
             "orders", "confirm", "123"],
            obj={},
        )
        assert json.loads(result.output)["error"].startswith("Refusing to confirm")

    def test_draft_flow_without_credentials(self, tmp_path):
        cli_mod = _fresh_cli()
        path = _session_path(tmp_path)
        runner = CliRunner()
        r1 = runner.invoke(cli_mod.cli, [
            "--json", "--session", path, "draft", "recipient",
            "--name", "Jane", "--address1", "1 St", "--city", "Berlin",
            "--country-code", "DE", "--zip", "10115",
        ], obj={})
        assert r1.exit_code == 0

        cli_mod._session = None
        r2 = runner.invoke(cli_mod.cli, [
            "--json", "--session", path, "draft", "add-item",
            "--variant-id", "4012", "--quantity", "2",
            "--image-url", "http://x/a.png",
        ], obj={})
        assert r2.exit_code == 0
        assert json.loads(r2.output)["summary"]["complete"] is True

    def test_config_set_rejects_unknown_key(self, tmp_path):
        cli_mod = _fresh_cli()
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--json", "--session", _session_path(tmp_path),
             "config", "set", "nope", "x"],
            obj={},
        )
        assert result.exit_code != 0
        assert "Unknown config key" in result.output

    def test_config_get_masks_api_key(self, tmp_path):
        cli_mod = _fresh_cli()
        auth_mod.save_config({"api_key": "secret-token-1234"})
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--json", "--session", _session_path(tmp_path), "config", "get"],
            obj={},
        )
        assert "secret-token" not in result.output
        assert "1234" in result.output

    def test_parse_ids_rejects_junk(self):
        cli_mod = _fresh_cli()
        with pytest.raises(ValueError, match="Invalid ID 'abc'"):
            cli_mod._parse_ids("1,abc,3")

    def test_parse_ids_handles_spaces_and_empties(self):
        cli_mod = _fresh_cli()
        assert cli_mod._parse_ids(" 1 , 2 ,, 3 ") == [1, 2, 3]
        assert cli_mod._parse_ids(None) == []

    def test_dry_run_suppresses_session_write(self, tmp_path):
        cli_mod = _fresh_cli()
        path = _session_path(tmp_path, "dry.json")
        CliRunner().invoke(cli_mod.cli, [
            "--json", "--dry-run", "--session", path, "draft", "add-item",
            "--variant-id", "1",
        ], obj={})
        assert not os.path.exists(path)

    def test_store_use_json_lists_instead_of_prompting(self, tmp_path, monkeypatch):
        """An agent must get the store list back, never a blocked prompt."""
        cli_mod = _fresh_cli()
        monkeypatch.setenv("PRINTFUL_API_KEY", "t")
        cli_mod._transport = FakeTransport([{"data": [
            {"id": 1, "name": "Alpha", "type": "native"},
            {"id": 2, "name": "Beta", "type": "square"},
        ]}])
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--json", "--session", _session_path(tmp_path), "store", "use"],
            obj={},
        )
        assert result.exit_code != 0
        error = json.loads(result.output)["error"]
        assert "not an interactive terminal" in error
        assert "Alpha" in error and "Beta" in error
        assert "store use <STORE_ID>" in error

    def test_store_use_with_id_sets_session(self, tmp_path):
        cli_mod = _fresh_cli()
        path = _session_path(tmp_path)
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--json", "--session", path, "store", "use", "1135966"],
            obj={},
        )
        assert result.exit_code == 0
        assert json.loads(result.output)["store_id"] == "1135966"
        assert json.load(open(path))["store_id"] == "1135966"

    def test_store_use_save_writes_config(self, tmp_path):
        cli_mod = _fresh_cli()
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--json", "--session", _session_path(tmp_path),
             "store", "use", "42", "--save"],
            obj={},
        )
        assert json.loads(result.output)["saved_to_config"] is True
        assert auth_mod.load_config()["store_id"] == "42"

    def test_store_id_error_gets_actionable_hint(self, tmp_path, monkeypatch):
        """The account-level token error must say how to fix itself."""
        cli_mod = _fresh_cli()
        monkeypatch.setenv("PRINTFUL_API_KEY", "t")
        cli_mod._transport = FakeTransport([PrintfulError(
            "This endpoint requires `store_id`!", status_code=400,
            detail={"data": "This endpoint requires `store_id`!",
                    "error": {"reason": "BadRequest",
                              "message": "This endpoint requires `store_id`!"}},
        )])
        result = CliRunner().invoke(
            cli_mod.cli,
            ["--json", "--session", _session_path(tmp_path), "store", "list"],
            obj={},
        )
        payload = json.loads(result.output)
        assert "store use" in payload["hint"]
        assert "account-level" in payload["hint"]

    def test_help_needs_no_credentials(self):
        cli_mod = _fresh_cli()
        result = CliRunner().invoke(cli_mod.cli, ["--help"], obj={})
        assert result.exit_code == 0
        assert "catalog" in result.output
