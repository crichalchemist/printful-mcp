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
