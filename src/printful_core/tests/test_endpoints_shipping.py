import pytest

from printful_core.endpoints import shipping

RECIPIENT = {"country_code": "US", "state_code": "NC", "zip": "28273"}


def test_countries_path():
    assert shipping.list_countries().path == "/countries"


def test_rates_path_and_method():
    req = shipping.calculate_rates(RECIPIENT, [{"catalog_variant_id": 4012, "quantity": 1}])
    assert req.method == "POST"
    assert req.path == "/shipping-rates"


def test_rates_default_missing_source():
    """The live API rejects an item without source: 'must be of type string'."""
    req = shipping.calculate_rates(RECIPIENT, [{"catalog_variant_id": 4012, "quantity": 1}])
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


def test_rates_do_not_alias_caller_recipient():
    """A caller reusing a recipient dict must not retroactively alter a built request."""
    recipient = dict(RECIPIENT)
    req = shipping.calculate_rates(recipient, [{"catalog_variant_id": 1, "quantity": 1}])
    recipient["zip"] = "99999"
    assert req.json["recipient"]["zip"] != "99999"


def test_tax_uses_v1():
    req = shipping.calculate_tax("US", state_code="CA", zip_code="90001")
    assert req.version == "v1"
    assert req.path == "/tax/rates"
    assert req.json["recipient"]["state_code"] == "CA"
