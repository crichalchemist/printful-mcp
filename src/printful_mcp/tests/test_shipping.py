"""The shipping adapter, including the pagination defect this tool used to have."""
import json

from printful_mcp.models.inputs import CalculateShippingInput, CalculateTaxInput
from printful_mcp.tools import shipping
from printful_mcp.tests.conftest import FakeTransport


async def test_the_country_list_walks_every_page():
    """A single request reports that Printful does not ship to the US.

    /v2/countries paginates at 20 of ~239 rows and `US` is late alphabetically,
    so the first page does not contain it. This is defect 4 from the spec, and
    it was live in this tool.
    """
    page_one = {"data": [{"code": "AT", "name": "Austria"}],
                "paging": {"total": 2, "limit": 1, "offset": 0}}
    page_two = {"data": [{"code": "US", "name": "United States"}],
                "paging": {"total": 2, "limit": 1, "offset": 1}}
    transport = FakeTransport([page_one, page_two])

    out = await shipping.list_countries(transport)

    assert len(transport.sent) == 2, "only the first page was fetched"
    assert "United States" in out
    assert "(2 total)" in out


async def test_rates_default_each_item_source_to_catalog(transport):
    """The endpoint rejects an item with a null source.

    'Property /order_items/0/source must be of type `string`, `null` provided'
    -- observed against the live API.
    """
    await shipping.calculate_shipping_rates(transport, CalculateShippingInput(
        recipient_country_code="US",
        items_json=json.dumps([{"catalog_variant_id": 4011, "quantity": 1}])))
    assert transport.last.json["order_items"][0]["source"] == "catalog"


async def test_tax_goes_to_v1(transport):
    """v2 exposes no tax endpoint, so this request must carry version v1.

    A v2 request to /tax/rates 404s, and the tool would report the destination
    as untaxed rather than unreachable.
    """
    await shipping.calculate_tax(
        transport, CalculateTaxInput(country_code="US", state_code="CA"))
    assert transport.last.version == "v1"
    assert transport.last.path == "/tax/rates"


async def test_malformed_items_json_is_reported_not_raised(transport):
    out = await shipping.calculate_shipping_rates(transport, CalculateShippingInput(
        recipient_country_code="US", items_json="not json"))
    assert "valid JSON" in out
    assert transport.sent == []
