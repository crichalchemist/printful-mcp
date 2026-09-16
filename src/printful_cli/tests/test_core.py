"""Unit tests for printful_cli.

Synthetic data and a mocked transport only — no network, no API key. The billable
endpoints (orders confirm) are asserted here against the fake transport precisely
because they must never be exercised live.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest
from click.testing import CliRunner

from printful_cli.core import catalog as catalog_mod
from printful_cli.core import files as files_mod
from printful_cli.core import mockups as mockups_mod
from printful_cli.core import orders as orders_mod
from printful_cli.core import shipping as shipping_mod
from printful_cli.core.session import (
    DraftOrder,
    PrintfulSession,
    _locked_save_json,
)
from printful_cli.utils import printful_backend as backend_mod
from printful_cli.utils.printful_backend import (
    PrintfulAuthError,
    PrintfulBackend,
    PrintfulError,
    PrintfulRateLimitError,
)


# --------------------------------------------------------------------------
# Fake transport
# --------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, raw=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self._raw = raw
        self.content = b"" if raw == b"" else b"x"

    def json(self):
        if self._raw is not None:
            raise ValueError("not json")
        return self._body


class FakeSession:
    """Records requests and replays queued responses."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return FakeResponse(200, {"data": {}})
        return self.responses.pop(0)

    def close(self):
        pass


def make_backend(responses=None, api_key="test-token", store_id=None) -> PrintfulBackend:
    backend = PrintfulBackend(api_key=api_key, store_id=store_id)
    backend.session = FakeSession(responses)
    return backend


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Keep tests off the developer's real env vars and config file."""
    monkeypatch.delenv("PRINTFUL_API_KEY", raising=False)
    monkeypatch.delenv("PRINTFUL_STORE_ID", raising=False)
    monkeypatch.setattr(backend_mod, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(backend_mod, "CONFIG_DIR", tmp_path)


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


# --------------------------------------------------------------------------
# Backend
# --------------------------------------------------------------------------

class TestCredentials:
    def test_explicit_key_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("PRINTFUL_API_KEY", "from-env")
        assert backend_mod.resolve_api_key("explicit") == "explicit"

    def test_env_used_when_no_explicit(self, monkeypatch):
        monkeypatch.setenv("PRINTFUL_API_KEY", "from-env")
        assert backend_mod.resolve_api_key() == "from-env"

    def test_config_used_when_no_env(self):
        backend_mod.save_config({"api_key": "from-config"})
        assert backend_mod.resolve_api_key() == "from-config"

    def test_env_beats_config(self, monkeypatch):
        backend_mod.save_config({"api_key": "from-config"})
        monkeypatch.setenv("PRINTFUL_API_KEY", "from-env")
        assert backend_mod.resolve_api_key() == "from-env"

    def test_missing_key_raises_with_instructions(self):
        with pytest.raises(PrintfulAuthError, match="printful.com/dashboard/api"):
            backend_mod.resolve_api_key()

    def test_store_id_resolution(self, monkeypatch):
        assert backend_mod.resolve_store_id() is None
        monkeypatch.setenv("PRINTFUL_STORE_ID", "42")
        assert backend_mod.resolve_store_id() == "42"
        assert backend_mod.resolve_store_id("7") == "7"


class TestBackendHeaders:
    def test_authorization_always_sent(self):
        b = make_backend([FakeResponse(200, {"data": []})])
        b.get("/countries")
        assert b.session.calls[0]["headers"]["Authorization"] == "Bearer test-token"

    def test_store_header_sent_when_set(self):
        b = make_backend([FakeResponse(200, {"data": []})], store_id="777")
        b.get("/orders")
        assert b.session.calls[0]["headers"]["X-PF-Store-Id"] == "777"

    def test_store_header_absent_when_unset(self):
        b = make_backend([FakeResponse(200, {"data": []})])
        b.get("/orders")
        assert "X-PF-Store-Id" not in b.session.calls[0]["headers"]

    def test_none_params_dropped(self):
        b = make_backend([FakeResponse(200, {"data": []})])
        b.get("/catalog-products", params={"limit": 5, "colors": None})
        assert b.session.calls[0]["params"] == {"limit": 5}


class TestBackendResponses:
    def test_v2_returns_body_unchanged(self):
        b = make_backend([FakeResponse(200, {"data": {"id": 1}})])
        assert b.get("/orders/1") == {"data": {"id": 1}}

    def test_v1_unwraps_result(self):
        b = make_backend([FakeResponse(200, {"code": 200, "result": [{"id": 9}]})])
        assert b.get("/store/products", version="v1") == [{"id": 9}]

    def test_v1_without_result_returns_body(self):
        b = make_backend([FakeResponse(200, {"other": 1})])
        assert b.get("/x", version="v1") == {"other": 1}

    def test_empty_body_returns_empty_dict(self):
        b = make_backend([FakeResponse(204, {}, raw=b"")])
        assert b.delete("/orders/1") == {}

    def test_non_json_success_raises(self):
        b = make_backend([FakeResponse(200, raw=b"<html>")])
        with pytest.raises(PrintfulError, match="Invalid JSON"):
            b.get("/x")


class TestBackendErrors:
    def test_v2_error_uses_detail(self):
        b = make_backend([FakeResponse(400, {"detail": "Bad variant", "title": "T"})])
        with pytest.raises(PrintfulError, match="Bad variant"):
            b.get("/x")

    def test_v2_error_falls_back_to_title(self):
        b = make_backend([FakeResponse(400, {"title": "Validation failed"})])
        with pytest.raises(PrintfulError, match="Validation failed"):
            b.get("/x")

    def test_v1_error_uses_error_message(self):
        b = make_backend([FakeResponse(404, {"code": 404,
                                             "error": {"message": "Not Found"}})])
        with pytest.raises(PrintfulError, match="Not Found"):
            b.get("/x", version="v1")

    # --- Regression: the live v2 API does NOT use RFC 9457 --------------
    # Verified against real 400 and 404 responses. Reading only detail/title
    # reduced every v2 error to "Unknown error" and hid the cause.

    def test_v2_error_reads_v1_style_envelope(self):
        """A live v2 400 body, captured verbatim."""
        b = make_backend([FakeResponse(400, {
            "data": "This endpoint requires `store_id`!",
            "error": {"reason": "BadRequest",
                      "message": "This endpoint requires `store_id`!"},
        })])
        with pytest.raises(PrintfulError, match="requires `store_id`"):
            b.post("/shipping-rates", json_data={})

    def test_v2_404_reads_v1_style_envelope(self):
        """A live v2 404 body, captured verbatim."""
        b = make_backend([FakeResponse(404, {
            "data": "Product 99999999 does not exist or is inactive.",
            "error": {"reason": "NotFound",
                      "message": "Product 99999999 does not exist or is inactive."},
        })])
        with pytest.raises(PrintfulError, match="does not exist or is inactive"):
            b.get("/catalog-products/99999999")

    def test_v2_error_never_degrades_to_unknown(self):
        b = make_backend([FakeResponse(400, {
            "data": "msg", "error": {"reason": "BadRequest", "message": "msg"}})])
        with pytest.raises(PrintfulError) as exc:
            b.get("/x")
        assert exc.value.message != "Unknown error"

    def test_error_message_from_data_string_only(self):
        b = make_backend([FakeResponse(400, {"data": "plain message"})])
        with pytest.raises(PrintfulError, match="plain message"):
            b.get("/x")

    def test_error_with_no_recognizable_shape_names_status(self):
        b = make_backend([FakeResponse(500, {"weird": {"nested": 1}})])
        with pytest.raises(PrintfulError, match="status 500"):
            b.get("/x")

    def test_error_body_preserved_in_detail(self):
        body = {"data": "m", "error": {"reason": "BadRequest", "message": "m"}}
        b = make_backend([FakeResponse(400, body)])
        with pytest.raises(PrintfulError) as exc:
            b.get("/x")
        assert exc.value.detail == body

    def test_401_mentions_expiry(self):
        b = make_backend([FakeResponse(401, {})])
        with pytest.raises(PrintfulAuthError, match="expire"):
            b.get("/x")

    def test_403_mentions_scope(self):
        b = make_backend([FakeResponse(403, {})])
        with pytest.raises(PrintfulAuthError, match="scope"):
            b.get("/x")

    @pytest.mark.parametrize("code", [429, 419])
    def test_rate_limit_carries_retry_after(self, code):
        b = make_backend([FakeResponse(code, {}, headers={"Retry-After": "30"})])
        with pytest.raises(PrintfulRateLimitError) as exc:
            b.get("/x")
        assert exc.value.retry_after == "30"

    def test_rate_limit_message_mentions_mockup_limits(self):
        b = make_backend([FakeResponse(429, {}, headers={"Retry-After": "60"})])
        with pytest.raises(PrintfulRateLimitError, match="2/60s new stores"):
            b.get("/x")

    def test_error_status_code_preserved(self):
        b = make_backend([FakeResponse(422, {"detail": "nope"})])
        with pytest.raises(PrintfulError) as exc:
            b.get("/x")
        assert exc.value.status_code == 422
        assert exc.value.to_dict()["status_code"] == 422


# --------------------------------------------------------------------------
# Orders
# --------------------------------------------------------------------------

class TestOrders:
    def test_update_rejects_empty_payload(self):
        with pytest.raises(ValueError, match="at least one field"):
            orders_mod.update_order(make_backend(), "1", {})

    def test_confirm_targets_confirmation_endpoint(self):
        """The billable endpoint — asserted here so it is never called live."""
        b = make_backend([FakeResponse(200, {"data": {"status": "pending"}})])
        orders_mod.confirm_order(b, "123")
        call = b.session.calls[0]
        assert call["method"] == "POST"
        assert call["url"].endswith("/v2/orders/123/confirmation")

    def test_cancel_issues_delete(self):
        b = make_backend([FakeResponse(204, {}, raw=b"")])
        result = orders_mod.cancel_order(b, "123")
        assert b.session.calls[0]["method"] == "DELETE"
        assert result["status"] == "cancelled"

    def test_create_posts_to_orders(self):
        b = make_backend([FakeResponse(200, {"data": {"id": 5}})])
        orders_mod.create_order(b, {"recipient": {}, "order_items": []})
        assert b.session.calls[0]["url"].endswith("/v2/orders")

    def test_estimate_polls_until_completed(self):
        b = make_backend([
            FakeResponse(200, {"data": {"id": "t1", "status": "pending"}}),
            FakeResponse(200, {"data": {"id": "t1", "status": "pending"}}),
            FakeResponse(200, {"data": {"id": "t1", "status": "completed",
                                        "costs": {"total": "25.00"}}}),
        ])
        result = orders_mod.estimate_costs(b, {}, interval=0, max_wait=5)
        assert result["data"]["status"] == "completed"

    def test_estimate_raises_on_failure_with_reasons(self):
        b = make_backend([
            FakeResponse(200, {"data": {"id": "t1", "status": "pending"}}),
            FakeResponse(200, {"data": {"id": "t1", "status": "failed",
                                        "failure_reasons": ["bad variant"]}}),
        ])
        with pytest.raises(PrintfulError, match="bad variant"):
            orders_mod.estimate_costs(b, {}, interval=0, max_wait=5)

    def test_estimate_timeout_names_task(self):
        b = make_backend([FakeResponse(200, {"data": {"id": "t9", "status": "pending"}})
                          for _ in range(10)])
        with pytest.raises(PrintfulError, match="t9"):
            orders_mod.estimate_costs(b, {}, interval=0, max_wait=0.01)

    def test_estimate_no_poll_returns_task(self):
        b = make_backend([FakeResponse(200, {"data": {"id": "t1", "status": "pending"}})])
        result = orders_mod.estimate_costs(b, {}, poll=False)
        assert result["data"]["id"] == "t1"

    def test_summarize_orders_handles_missing_costs(self):
        summary = orders_mod.summarize_orders({"data": [{"id": 1, "status": "draft"}]})
        assert summary["orders"][0]["total"] is None
        assert summary["count"] == 1

    def test_summarize_orders_empty(self):
        assert orders_mod.summarize_orders({})["count"] == 0


# --------------------------------------------------------------------------
# Mockups
# --------------------------------------------------------------------------

class TestMockups:
    def test_create_requires_variants(self):
        with pytest.raises(ValueError, match="variant ID"):
            mockups_mod.create_task(make_backend(), 71, [], "http://x/a.png")

    def test_create_requires_image(self):
        with pytest.raises(ValueError, match="image URL"):
            mockups_mod.create_task(make_backend(), 71, [1], "")

    def test_create_builds_nested_payload(self):
        b = make_backend([FakeResponse(200, {"data": {"id": "t1"}})])
        mockups_mod.create_task(b, 71, [4012], "http://x/a.png",
                                mockup_style_ids=[5])
        product = b.session.calls[0]["json"]["products"][0]
        assert product["catalog_product_id"] == 71
        assert product["catalog_variant_ids"] == [4012]
        assert product["mockup_style_ids"] == [5]
        assert product["placements"][0]["layers"][0]["url"] == "http://x/a.png"

    def test_wait_raises_on_failed(self):
        b = make_backend([FakeResponse(200, {"data": {"status": "failed",
                                                      "reason": "bad file"}})])
        with pytest.raises(PrintfulError, match="bad file"):
            mockups_mod.wait_for_task(b, "t1", max_wait=5, interval=0)

    def test_wait_timeout_names_task(self):
        b = make_backend([FakeResponse(200, {"data": {"status": "pending"}})
                          for _ in range(5)])
        with pytest.raises(PrintfulError, match="t7"):
            mockups_mod.wait_for_task(b, "t7", max_wait=0.01, interval=0)

    def test_extract_urls_primary_and_extra(self):
        data = {"data": [{"mockups": [
            {"mockup_url": "http://x/1.jpg", "extra": [{"url": "http://x/2.jpg"}]}
        ]}]}
        assert mockups_mod.extract_mockup_urls(data) == [
            "http://x/1.jpg", "http://x/2.jpg"
        ]

    def test_extract_urls_empty(self):
        assert mockups_mod.extract_mockup_urls({}) == []

    def test_extract_urls_malformed(self):
        assert mockups_mod.extract_mockup_urls({"data": ["junk"]}) == []


# --------------------------------------------------------------------------
# Catalog / shipping / files summarizers
# --------------------------------------------------------------------------

class TestSummarizers:
    def test_products_empty(self):
        assert catalog_mod.summarize_products({})["count"] == 0

    def test_products_partial_payload(self):
        out = catalog_mod.summarize_products({"data": [{"id": 1, "name": "Tee"}]})
        assert out["products"][0]["type"] is None
        assert out["products"][0]["techniques"] == ""

    def test_variants_empty(self):
        assert catalog_mod.summarize_variants({})["count"] == 0

    def test_rates_empty(self):
        assert shipping_mod.summarize_rates({})["count"] == 0

    def test_countries_counts_states(self):
        out = shipping_mod.summarize_countries(
            {"data": [{"code": "US", "name": "United States", "states": [1, 2]}]}
        )
        assert out["countries"][0]["states"] == 2

    def test_countries_without_states_key(self):
        out = shipping_mod.summarize_countries({"data": [{"code": "DE"}]})
        assert out["countries"][0]["states"] == 0


class TestCountriesPagination:
    """Regression: /v2/countries defaults to 20 of ~239 rows and omits 'US'."""

    def _pages(self):
        return [
            FakeResponse(200, {"data": [{"code": "AF"}, {"code": "AL"}],
                               "paging": {"total": 5, "limit": 2, "offset": 0}}),
            FakeResponse(200, {"data": [{"code": "DE"}, {"code": "GB"}],
                               "paging": {"total": 5, "limit": 2, "offset": 2}}),
            FakeResponse(200, {"data": [{"code": "US"}],
                               "paging": {"total": 5, "limit": 2, "offset": 4}}),
        ]

    def test_fetches_every_page(self):
        b = make_backend(self._pages())
        data = shipping_mod.list_countries(b)
        codes = [c["code"] for c in data["data"]]
        assert codes == ["AF", "AL", "DE", "GB", "US"]
        assert data["paging"]["returned"] == 5
        assert len(b.session.calls) == 3

    def test_us_present_after_pagination(self):
        b = make_backend(self._pages())
        summary = shipping_mod.summarize_countries(shipping_mod.list_countries(b))
        assert "US" in {c["code"] for c in summary["countries"]}
        assert summary["count"] == 5

    def test_opt_out_makes_one_call(self):
        b = make_backend(self._pages())
        shipping_mod.list_countries(b, all_pages=False)
        assert len(b.session.calls) == 1

    def test_first_request_uses_page_limit(self):
        b = make_backend(self._pages())
        shipping_mod.list_countries(b, all_pages=False)
        assert b.session.calls[0]["params"]["limit"] == shipping_mod.PAGE_LIMIT

    def test_missing_paging_returns_first_page(self):
        b = make_backend([FakeResponse(200, {"data": [{"code": "US"}]})])
        data = shipping_mod.list_countries(b)
        assert len(data["data"]) == 1

    def test_empty_page_breaks_loop(self):
        b = make_backend([
            FakeResponse(200, {"data": [{"code": "AF"}],
                               "paging": {"total": 99, "limit": 1, "offset": 0}}),
            FakeResponse(200, {"data": [], "paging": {"total": 99, "limit": 1}}),
        ])
        data = shipping_mod.list_countries(b)
        assert len(data["data"]) == 1


class TestShipping:
    def test_rates_requires_items(self):
        with pytest.raises(ValueError, match="at least one item"):
            shipping_mod.calculate_rates(make_backend(), {"country_code": "US"}, [])

    # --- Regression: live shipping-rates rejects an item without `source`
    # ("must be of type `string`, `null` provided").

    def test_rates_defaults_missing_source(self):
        b = make_backend([FakeResponse(200, {"data": []})])
        shipping_mod.calculate_rates(
            b, {"country_code": "US"}, [{"catalog_variant_id": 4012, "quantity": 1}]
        )
        sent = b.session.calls[0]["json"]["order_items"][0]
        assert sent["source"] == "catalog"

    def test_rates_preserves_explicit_source(self):
        b = make_backend([FakeResponse(200, {"data": []})])
        shipping_mod.calculate_rates(
            b, {"country_code": "US"},
            [{"source": "sync_product", "catalog_variant_id": 1, "quantity": 1}],
        )
        assert b.session.calls[0]["json"]["order_items"][0]["source"] == "sync_product"

    def test_rates_does_not_mutate_caller_items(self):
        b = make_backend([FakeResponse(200, {"data": []})])
        items = [{"catalog_variant_id": 4012, "quantity": 1}]
        shipping_mod.calculate_rates(b, {"country_code": "US"}, items)
        assert "source" not in items[0]

    # --- Regression: rate rows are keyed `shipping` / `shipping_method_name`,
    # not `id` / `name`. Body captured from a live response.

    def test_summarize_rates_reads_live_keys(self):
        live = {"data": [{
            "shipping": "STANDARD",
            "shipping_method_name": "Flat Rate (Estimated delivery: Sep 23-25)",
            "rate": "4.95", "currency": "USD",
            "min_delivery_days": 4, "max_delivery_days": 6,
            "min_delivery_date": "2026-09-23", "max_delivery_date": "2026-09-25",
        }]}
        row = shipping_mod.summarize_rates(live)["rates"][0]
        assert row["id"] == "STANDARD"
        assert row["name"].startswith("Flat Rate")
        assert row["rate"] == "4.95"
        assert row["min_date"] == "2026-09-23"

    def test_summarize_rates_falls_back_to_id_name(self):
        legacy = {"data": [{"id": "X", "name": "Legacy", "rate": "1.00"}]}
        row = shipping_mod.summarize_rates(legacy)["rates"][0]
        assert row["id"] == "X"
        assert row["name"] == "Legacy"

    def test_tax_targets_v1(self):
        b = make_backend([FakeResponse(200, {"code": 200, "result": {"rate": 0.08}})])
        shipping_mod.calculate_tax(b, "US", "CA", "LA", "90001")
        call = b.session.calls[0]
        assert "/v2/" not in call["url"]
        assert call["url"].endswith("/tax/rates")
        assert call["json"]["recipient"]["state_code"] == "CA"


class TestFiles:
    def test_add_requires_url(self):
        with pytest.raises(ValueError, match="URL is required"):
            files_mod.add_file(make_backend(), "")

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
    printful_cli._backend = None
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
        assert cli_mod._backend is None

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
        backend_mod.save_config({"api_key": "secret-token-1234"})
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
        cli_mod._backend = make_backend([FakeResponse(200, {"data": [
            {"id": 1, "name": "Alpha", "type": "native"},
            {"id": 2, "name": "Beta", "type": "square"},
        ]})])
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
        assert backend_mod.load_config()["store_id"] == "42"

    def test_store_id_error_gets_actionable_hint(self, tmp_path, monkeypatch):
        """The account-level token error must say how to fix itself."""
        cli_mod = _fresh_cli()
        monkeypatch.setenv("PRINTFUL_API_KEY", "t")
        cli_mod._backend = make_backend([FakeResponse(400, {
            "data": "This endpoint requires `store_id`!",
            "error": {"reason": "BadRequest",
                      "message": "This endpoint requires `store_id`!"},
        })])
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
