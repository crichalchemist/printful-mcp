"""The catalog adapter: what Request each tool builds, and what it returns."""

import json

from printful_core.errors import PrintfulError
from printful_mcp.models.inputs import (
    GetCategoryInput,
    GetProductVariantsInput,
    GetSizeGuideInput,
    ListCatalogProductsInput,
    ListCategoriesInput,
)
from printful_mcp.tools import catalog


async def test_filters_reach_the_query_string(transport):
    """A filter the user set must not be silently dropped.

    Every filter is optional and each is threaded through its own argument, so
    a dropped one returns a plausible unfiltered catalog rather than an error.
    """
    await catalog.list_catalog_products(
        transport,
        ListCatalogProductsInput(
            limit=5,
            offset=10,
            category_ids="24,25",
            colors="Black",
            techniques="dtg",
            types="T-SHIRT",
        ),
    )
    sent = transport.last
    assert sent.method == "GET"
    assert sent.path == "/catalog-products"
    assert sent.params == {
        "limit": 5,
        "offset": 10,
        "category_ids": "24,25",
        "colors": "Black",
        "techniques": "dtg",
        "types": "T-SHIRT",
    }


async def test_the_callers_page_is_sent_unchanged(transport):
    """Variant listing must not silently collect every page.

    `collect_pages_async` would be wrong here: the tool exposes limit and
    offset, so walking the whole collection ignores what the caller asked for
    and can return thousands of rows into a model's context.
    """
    await catalog.get_product_variants(
        transport, GetProductVariantsInput(product_id=71, limit=2, offset=40)
    )
    assert len(transport.sent) == 1
    assert transport.last.params == {"limit": 2, "offset": 40}


async def test_an_unset_size_guide_unit_is_omitted(transport):
    """An absent unit must not reach the API as the string 'None'."""
    await catalog.get_size_guide(transport, GetSizeGuideInput(product_id=71))
    assert "unit" not in transport.last.params


async def test_an_api_error_is_returned_as_text(transport):
    """An MCP client must see a readable string, never a traceback.

    The tool contract is that errors are returned. A raised exception crosses
    the JSON-RPC boundary as a protocol error, and the calling model sees
    nothing it can act on.
    """
    transport._responses.append(PrintfulError("Category 999 not found", status_code=404))
    out = await catalog.get_category(transport, GetCategoryInput(category_id=999))
    assert out == "Error: Category 999 not found"


async def test_json_format_returns_the_body_verbatim(transport):
    """`format="json"` exists so a caller can parse rather than scrape."""
    transport._responses.append({"data": [{"id": 24, "title": "Men's"}], "paging": {"total": 1}})
    out = await catalog.list_categories(transport, ListCategoriesInput(format="json"))
    assert json.loads(out)["data"][0]["id"] == 24
