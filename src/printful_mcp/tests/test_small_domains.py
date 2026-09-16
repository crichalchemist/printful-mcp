"""files, stores and sync: what each tool sends and what it renders."""
from printful_mcp.models.inputs import (
    AddFileInput,
    GetStoreStatsInput,
    ListStoreTemplatesInput,
)
from printful_mcp.tools import files, stores, sync
from printful_mcp.tools.sync import ListSyncProductsInput


async def test_store_templates_send_paging_not_a_product_id(transport):
    """`stores.list_templates` takes limit and offset, not an id.

    Its namesake `mockups.list_templates(product_id)` takes a required id, so a
    positional call here binds that id to `limit` and silently returns the
    wrong collection with no error.
    """
    await stores.list_store_templates(
        transport, ListStoreTemplatesInput(limit=5, offset=10))
    assert transport.last.path == "/product-templates"
    assert transport.last.params == {"limit": 5, "offset": 10}


async def test_sync_products_are_a_v1_request(transport):
    """v2 exposes no sync-product endpoint.

    A v2 request 404s, and the tool would report an empty store rather than an
    unreachable endpoint.
    """
    await sync.list_sync_products(transport, ListSyncProductsInput())
    assert transport.last.version == "v1"


async def test_file_visibility_reaches_the_request(transport):
    """`visible=False` keeps a working file out of the user's library.

    Dropping it silently makes every uploaded file visible.
    """
    # markdown.file_added reads id/status/url unguarded, so the empty-queue
    # default {"data": {}} would raise KeyError inside the tool's try block.
    transport._responses.append({"data": {
        "id": 9, "status": "waiting", "url": "https://example.com/art.png"}})
    await files.add_file(transport, AddFileInput(
        url="https://example.com/art.png", visible=False))
    assert transport.last.json["visible"] is False


async def test_a_file_still_processing_says_so(transport):
    """Status 'waiting' is the normal first answer for a large upload.

    Rendering it as a finished file shows blank dimensions and no preview.
    """
    transport._responses.append({"data": {
        "id": 9, "status": "waiting", "url": "https://example.com/art.png"}})
    out = await files.add_file(transport, AddFileInput(url="https://example.com/art.png"))
    assert "being processed" in out


async def test_store_statistics_pass_the_date_window_through(transport):
    await stores.get_store_statistics(transport, GetStoreStatsInput(
        store_id=12345678, date_from="2026-01-01", date_to="2026-01-31"))
    assert transport.last.params["date_from"] == "2026-01-01"
    assert transport.last.params["date_to"] == "2026-01-31"
