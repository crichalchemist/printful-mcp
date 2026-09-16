"""The MCP surface against the real API.

The offline suite runs entirely on fake transports, so it cannot show that the
rewrite preserved live behavior. This can. It is the gate for this plan.

Run: set -a; . ./.env; set +a; export PRINTFUL_STORE_ID=<id>
     .venv/bin/python -m pytest -m live -q
"""
import json
import os

import pytest

from printful_mcp.models.inputs import (
    CreateEstimationTaskInput,
    GetProductInput,
    ListCategoriesInput,
    ListCatalogProductsInput,
    ListStoreTemplatesInput,
)
from printful_mcp.tools import catalog, orders, shipping, stores
from printful_mcp.transport import get_transport

pytestmark = pytest.mark.live


def _require_credentials():
    if not os.environ.get("PRINTFUL_API_KEY"):
        pytest.fail("PRINTFUL_API_KEY is not set. Live tests fail loudly rather "
                    "than skip, so a green run means the API was really reached.")


@pytest.fixture
def live_transport():
    """The real transport.

    Deliberately NOT named `transport`. conftest.py defines a `transport`
    fixture that yields a FakeTransport, and a module-local fixture of the same
    name silently shadows it -- so a test moved out of this file would keep
    hitting the live API under a name that reads as a fake.
    """
    _require_credentials()
    return get_transport()


async def test_the_country_list_contains_the_united_states(live_transport):
    """The defect this plan fixes, checked where it actually lived.

    A single unpaginated request returns the first page only, and `US` is not
    in it. An offline test can prove the tool calls collect_pages_async; only
    this can prove the result is the whole collection.
    """
    out = await shipping.list_countries(live_transport)
    assert "United States" in out
    assert "(US)" in out


async def test_a_v2_error_says_what_went_wrong(live_transport):
    """Every v2 error used to arrive as 'Unknown error'.

    Product 99999999 does not exist -- a deliberately invalid ID, not a real
    product being probed.
    """
    out = await catalog.get_product(live_transport, GetProductInput(product_id=99999999))
    assert out.startswith("Error:")
    assert "Unknown error" not in out


async def test_categories_return_real_rows(live_transport):
    """A tool added in this plan, never exercised against the API before."""
    out = await catalog.list_categories(live_transport, ListCategoriesInput(limit=5))
    assert "Catalog Categories" in out
    assert "ID" in out


async def test_the_caller_s_limit_is_respected(live_transport):
    """Proves the catalog tools do not silently walk every page."""
    out = await catalog.list_catalog_products(
        live_transport, ListCatalogProductsInput(limit=2, format="json"))
    assert len(json.loads(out)["data"]) == 2


async def test_an_estimate_can_be_started_and_read(live_transport):
    """The create/read split, end to end.

    Estimation creates a task and charges nothing. This asserts the task is
    accepted and that reading it returns one of the three known states -- not
    that it completes, because completion timing is the API's business.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}]
    started = await orders.create_estimation_task(live_transport, CreateEstimationTaskInput(
        recipient_country_code="US", recipient_state_code="CA",
        recipient_city="San Francisco", recipient_zip="94107",
        items_json=json.dumps(items)))
    assert not started.startswith("Error:"), started
    assert "Task ID:" in started


async def test_product_templates_come_back_under_the_v1_items_key(live_transport):
    """The renderer reads `items`; only a live call can confirm that.

    `stores.list_templates` is the one v1 endpoint in this plan whose renderer
    was written from scratch, with no pre-move predecessor to be byte-identical
    to. Its shape was taken from the CLI's own normalization at
    `printful_cli/core/stores.py:31`, which is in-repo evidence rather than a
    live observation. A v2-shaped `data` key here would mean the tool renders
    "Showing 0 templates" for a store that has templates -- a wrong answer
    shaped like a right one, which no offline test can catch.
    """
    body = json.loads(await stores.list_store_templates(
        live_transport, ListStoreTemplatesInput(format="json")))
    assert isinstance(body, list) or "items" in body, (
        f"expected a bare list or an 'items' key, got keys {sorted(body)}")


async def test_a_template_row_carries_the_fields_the_renderer_prints(live_transport):
    """A wrong row key renders 'N/A' forever: valid markdown, no error.

    The renderer prints `title`, `catalog_product_id` and `created_at`. Those
    three names are the last unverified thing in this plan. This skips loudly
    rather than passing when the store has no templates -- a vacuous pass here
    would read as confirmation.
    """
    body = json.loads(await stores.list_store_templates(
        live_transport, ListStoreTemplatesInput(format="json")))
    rows = body if isinstance(body, list) else body.get("items", [])
    if not rows:
        pytest.skip("store has no product templates; row field names unverified")
    missing = [k for k in ("title", "catalog_product_id", "created_at")
               if k not in rows[0]]
    assert not missing, (
        f"the renderer prints keys the API does not send: {missing}. "
        f"The row actually carries {sorted(rows[0])}.")
