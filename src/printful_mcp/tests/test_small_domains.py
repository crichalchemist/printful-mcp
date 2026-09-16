"""files, stores and sync: what each tool sends and what it renders."""
from printful_mcp.models.inputs import (
    AddFileInput,
    GetFileInput,
    GetStoreStatsInput,
    ListStoresInput,
    ListStoreTemplatesInput,
)
from printful_mcp.tools import files, stores, sync
from printful_mcp.tools.sync import GetSyncProductInput, ListSyncProductsInput


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


async def test_product_templates_render_the_v1_items_key(transport):
    """v1 returns its rows under `items`; a v2 `data` read renders an empty page.

    The store has templates and the tool says "Showing 0 templates" -- a wrong
    answer that looks like a correct one, which is why this asserts on a row
    that must appear rather than on the count line alone.
    """
    transport._responses.append({
        "items": [{"id": 77, "title": "Summer Tee", "product_id": 71}],
        "paging": {"total": 1},
    })
    out = await stores.list_store_templates(transport, ListStoreTemplatesInput())
    assert "Summer Tee" in out
    assert "Showing 1 templates" in out
    assert "71" in out


async def test_a_bare_list_of_templates_still_renders(transport):
    """v1 sometimes hands back the list itself rather than an items envelope.

    `.get` on a list raises AttributeError, which is not a PrintfulError and
    escapes the tool as a traceback rather than the string an MCP client expects.
    """
    transport._responses.append([{"id": 77, "title": "Summer Tee"}])
    out = await stores.list_store_templates(transport, ListStoreTemplatesInput())
    assert "Summer Tee" in out


async def test_sync_products_are_a_v1_request(transport):
    """v2 exposes no sync-product endpoint.

    A v2 request 404s, and the tool would report an empty store rather than an
    unreachable endpoint. `sync.get_product` is also a v1 request, so pinning
    only the version would stay green if the tool called that builder instead
    -- assert the path too.
    """
    await sync.list_sync_products(transport, ListSyncProductsInput())
    assert transport.last.version == "v1"
    assert transport.last.path == "/store/products"


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

    Both `file_added` and `file_detail` contain the substring "being
    processed", so asserting on it alone passes even if `add_file` rendered
    through the wrong one. `file_added`'s message is useful because it tells
    the caller what to do next -- assert on that part specifically.
    """
    transport._responses.append({"data": {
        "id": 9, "status": "waiting", "url": "https://example.com/art.png"}})
    out = await files.add_file(transport, AddFileInput(url="https://example.com/art.png"))
    assert "Check status with printful_get_file" in out


async def test_store_statistics_pass_the_date_window_through(transport):
    """The rendered header must carry the requested window, not just the request.

    `store_statistics` takes `date_from`/`date_to` as arguments instead of
    reading them from the body because the response doesn't carry them back --
    nothing verified that wiring reached the rendered text until this assertion.
    """
    transport._responses.append({"data": {"store_id": 12345678, "currency": "USD"}})
    out = await stores.get_store_statistics(transport, GetStoreStatsInput(
        store_id=12345678, date_from="2026-01-01", date_to="2026-01-31"))
    assert transport.last.params["date_from"] == "2026-01-01"
    assert transport.last.params["date_to"] == "2026-01-31"
    assert "2026-01-01 to 2026-01-31" in out


async def test_get_file_looks_up_the_requested_file_id(transport):
    """The wrong endpoint here returns another file's status and URLs.

    A caller checking whether their upload finished would be told about
    someone else's file instead.
    """
    transport._responses.append({"data": {
        "id": 9, "status": "waiting", "created": "2026-01-01"}})
    await files.get_file(transport, GetFileInput(file_id=9))
    assert transport.last.path == "/files/9"


async def test_list_stores_reaches_the_store_list_endpoint(transport):
    """The wrong endpoint here silently returns the wrong resource entirely.

    `printful_list_stores` is how a multi-store account discovers its store
    IDs; reaching another endpoint would return unrelated or empty data with
    no error.
    """
    await stores.list_stores(transport, ListStoresInput())
    assert transport.last.path == "/stores"


async def test_get_sync_product_looks_up_the_requested_product(transport):
    """The wrong endpoint here renders a different sync product's variants.

    A caller asking for one product's saved design would silently see
    another product's data instead.
    """
    transport._responses.append({
        "sync_product": {"id": 1, "name": "Tee"},
        "sync_variants": [],
    })
    await sync.get_sync_product(transport, GetSyncProductInput(sync_product_id=1))
    assert transport.last.path == "/store/products/1"
