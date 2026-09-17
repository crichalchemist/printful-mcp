"""The orders adapter."""

import json

import pytest

from printful_core.errors import PrintfulError
from printful_mcp.models.inputs import (
    CancelOrderInput,
    ConfirmOrderInput,
    CreateEstimationTaskInput,
    CreateOrderInput,
    GetEstimationTaskInput,
    ListOrderItemsInput,
    ListOrderShipmentsInput,
    ListOrdersInput,
    UpdateOrderInput,
)
from printful_mcp.tools import orders


def _recipient():
    return {
        "recipient_name": "Ada Lovelace",
        "recipient_address1": "1 Analytical Way",
        "recipient_city": "London",
        "recipient_country_code": "GB",
        "recipient_zip": "EC1A 1BB",
    }


async def test_a_draft_order_carries_its_items(transport):
    """An order created without items can never be filled.

    This is the defect the upstream fix exists for: the tool used to send a
    recipient and nothing else, and the resulting draft was a dead end.
    """
    items = [
        {
            "source": "catalog",
            "catalog_variant_id": 4012,
            "quantity": 2,
            "placements": [
                {
                    "placement": "front",
                    "technique": "dtg",
                    "layers": [{"type": "file", "url": "https://x/a.png"}],
                }
            ],
        }
    ]
    transport._responses.append(
        {"data": {"id": 1, "status": "draft", "created_at": "", "updated_at": ""}}
    )
    await orders.create_order(
        transport, CreateOrderInput(items_json=json.dumps(items), **_recipient())
    )
    sent = transport.last
    assert sent.method == "POST"
    assert sent.path == "/orders"
    assert sent.json["order_items"][0]["catalog_variant_id"] == 4012
    assert sent.json["order_items"][0]["quantity"] == 2


async def test_the_status_filter_reaches_the_query(transport):
    """Without this the tool cannot answer 'which drafts are waiting?'."""
    await orders.list_orders(transport, ListOrdersInput(status="draft"))
    assert transport.last.params["status"] == "draft"


async def test_an_unset_status_is_not_sent(transport):
    """A literal 'None' status would filter every order out."""
    await orders.list_orders(transport, ListOrdersInput())
    assert "status" not in transport.last.params


async def test_confirmation_posts_to_the_confirmation_path(transport):
    """Confirmation charges the account, so the path must be exact.

    This tool is never exercised against the live API. A fake transport is the
    only place its request shape can be checked at all.
    """
    transport._responses.append(
        {"data": {"id": 42, "status": "pending", "created_at": "", "updated_at": ""}}
    )
    out = await orders.confirm_order(transport, ConfirmOrderInput(order_id="42"))
    assert transport.last.method == "POST"
    assert transport.last.path == "/orders/42/confirmation"
    assert "confirmed successfully" in out


async def test_a_core_validation_error_does_not_escape_as_a_traceback(transport):
    """The core raises ValueError; PrintfulError alone would not catch it.

    An uncaught exception crosses the JSON-RPC boundary as a protocol error,
    so the calling model sees a transport failure rather than the reason its
    order was rejected.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}]
    out = await orders.create_order(
        transport, CreateOrderInput(items_json=json.dumps(items), **_recipient())
    )
    assert out.startswith("Error: order_items[0] (variant 4012) has no placements.")
    assert '"placement":"front"' in out
    assert transport.sent == []


async def test_an_api_error_is_returned_as_text(transport):
    transport._responses.append(PrintfulError("Order 9 not found", status_code=404))
    out = await orders.list_orders(transport, ListOrdersInput())
    assert out == "Error: Order 9 not found"


async def test_the_order_list_shows_each_orders_status(transport):
    """'Which drafts are waiting?' is unanswerable if the row omits status."""
    transport._responses.append(
        {
            "data": [{"id": 7, "status": "draft", "created_at": "2026-01-01"}],
            "paging": {"total": 1, "offset": 0, "limit": 20},
        }
    )
    out = await orders.list_orders(transport, ListOrdersInput())
    assert "- **Status:** draft" in out


async def test_an_update_sends_a_patch_with_only_the_changed_fields(transport):
    """A PUT-shaped update would blank every field the caller omitted."""
    # Queue a renderable body: update_order renders markdown.order(), which reads
    # id/status/created_at/updated_at unguarded. The empty-queue default
    # {"data": {}} would raise KeyError inside the tool's try, and `except
    # PrintfulError` does not catch it -- the failure would read as a tool bug.
    transport._responses.append(
        {
            "data": {
                "id": 42,
                "status": "draft",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
            }
        }
    )
    await orders.update_order(
        transport,
        UpdateOrderInput(order_id="42", changes_json='{"recipient":{"address1":"2 New Street"}}'),
    )
    assert transport.last.method == "PATCH"
    assert transport.last.path == "/orders/42"
    assert transport.last.json == {"recipient": {"address1": "2 New Street"}}


async def test_an_empty_update_is_refused_before_sending(transport):
    """The core refuses a no-op PATCH; the tool must report it, not crash.

    `update_order` raises ValueError on an empty change set, which is not a
    PrintfulError and escapes a body that catches only that.
    """
    out = await orders.update_order(transport, UpdateOrderInput(order_id="42", changes_json="{}"))
    assert out.startswith("Error:")
    assert transport.sent == []


async def test_malformed_update_json_is_reported_not_raised(transport):
    out = await orders.update_order(
        transport, UpdateOrderInput(order_id="42", changes_json="not json")
    )
    assert "valid JSON" in out
    assert transport.sent == []


async def test_cancel_sends_a_delete(transport):
    """Cancel is destructive; the verb is what makes it so."""
    transport._responses.append({"data": {"id": 42}})
    out = await orders.cancel_order(transport, CancelOrderInput(order_id="42"))
    assert transport.last.method == "DELETE"
    assert transport.last.path == "/orders/42"
    assert "cancelled" in out


async def test_an_unshipped_order_says_so_rather_than_showing_an_empty_heading(transport):
    """`{"data": []}` is the normal answer for an order still in production."""
    transport._responses.append({"data": []})
    out = await orders.list_order_shipments(transport, ListOrderShipmentsInput(order_id="42"))
    assert "No shipments yet" in out


async def test_order_items_show_the_variant_and_quantity_needed_to_reorder(transport):
    """`markdown.order_items` reads every field through `.get()`, so a wrong or
    dropped key would not KeyError -- it would silently render 'N/A' and pass.
    Without this test, someone restocking or debugging a mis-shipped order could
    be shown the wrong variant or quantity and never know the renderer was broken.
    """
    transport._responses.append(
        {
            "data": [
                {
                    "id": 99,
                    "name": "Bella Canvas Tee",
                    "catalog_variant_id": 4012,
                    "quantity": 3,
                    "price": "12.00",
                    "currency": "USD",
                }
            ]
        }
    )
    out = await orders.list_order_items(transport, ListOrderItemsInput(order_id="42"))
    assert transport.last.method == "GET"
    assert transport.last.path == "/orders/42/order-items"
    assert "**Variant:** 4012" in out
    assert "**Quantity:** 3" in out


async def test_a_pending_estimate_tells_the_caller_to_come_back(transport):
    """A pending task must not render as an estimate of zero.

    `classify_task` returns "pending" for anything that is neither completed
    nor failed, and the costs block is absent in that state.
    """
    transport._responses.append({"data": {"id": "t1", "status": "pending"}})
    out = await orders.get_estimation_task(transport, GetEstimationTaskInput(task_id="t1"))
    assert "pending" in out
    assert "printful_get_estimation_task again" in out


async def test_a_list_shaped_task_body_is_unwrapped(transport):
    """The API returns this task as a one-element list, not an object.

    `task_body` handles both. A tool that read `data` directly would render a
    list where a dict is expected and report every estimate as pending.
    """
    transport._responses.append(
        {
            "data": [
                {"id": "t2", "status": "completed", "costs": {"currency": "USD", "total": "24.95"}}
            ]
        }
    )
    out = await orders.get_estimation_task(transport, GetEstimationTaskInput(task_id="t2"))
    assert "completed" in out
    assert "24.95" in out


async def test_a_failed_estimate_reports_why(transport):
    transport._responses.append(
        {
            "data": {
                "id": "t3",
                "status": "failed",
                "failure_reasons": ["No shipping to that country"],
            }
        }
    )
    out = await orders.get_estimation_task(transport, GetEstimationTaskInput(task_id="t3"))
    assert "failed" in out
    assert "No shipping to that country" in out


async def test_a_partial_estimation_task_record_reads_as_unknown_not_none(transport):
    """A task record missing a key must not tell the caller its ID is "None".

    The same defect class as the `body['id']` reads in tools/mockups.py, but the
    non-raising half of it: `.get()` with no default cannot raise, so nothing
    escapes the tool's `try` -- it simply renders a Python `None` into prose and
    hands the caller a task ID they cannot use. `mockups.py` degrades to
    'unknown'; this does too, so the two surfaces answer a partial record the
    same way.

    The `try` mirrors the mockups test and the two cases above it: it is the
    file's idiom for "this must return, never raise", and it would catch a
    future rewrite of `.get` back into a subscript.
    """
    params = CreateEstimationTaskInput(
        recipient_country_code="US",
        items_json=json.dumps([{"source": "sync_product", "sync_variant_id": 5, "quantity": 1}]),
    )

    transport._responses.append({"data": {"status": "pending"}})
    try:
        out = await orders.create_estimation_task(transport, params)
    except Exception as exc:  # noqa: BLE001 - must catch any escape to report it via pytest.fail
        pytest.fail(
            f"create_estimation_task raised {type(exc).__name__}: {exc} on a record with no id"
        )
    assert "Task ID: unknown" in out
    assert "Status: pending" in out

    transport._responses.append({"data": {"id": "e9"}})
    try:
        out = await orders.create_estimation_task(transport, params)
    except Exception as exc:  # noqa: BLE001 - must catch any escape to report it via pytest.fail
        pytest.fail(
            f"create_estimation_task raised {type(exc).__name__}: {exc} on a record with no status"
        )
    assert "Task ID: e9" in out
    assert "Status: unknown" in out


async def test_an_estimate_with_no_artwork_is_sent_not_refused_locally(transport):
    """The core builder deliberately does not guard placements for an estimate.

    The live API *does* reject a catalog item with no placements here, with the
    same message the order endpoint gives, and it rejects on the initial POST.
    That contract is established by the live test
    `TestLiveDraftOrder::test_estimation_rejects_an_item_with_no_artwork` in
    src/printful_cli/tests/test_full_e2e.py -- follow that pointer rather than
    re-deriving it here, and note that a FakeTransport like this one can never
    establish it.

    What this test pins is the decision not to pre-empt that rejection locally.
    `create_order` guards placements; `create_estimation_task` does not, and the
    asymmetry is deliberate rather than an oversight: a local guard raises
    before the request is sent, so the live test above would stop reaching
    Printful at all and the only evidence of the API's real behaviour would be
    destroyed. Estimation is free and places no order, so learning it from the
    API costs one round trip on a call that charges nothing.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}]
    out = await orders.create_estimation_task(
        transport,
        CreateEstimationTaskInput(
            recipient_country_code="US", recipient_state_code="CA", items_json=json.dumps(items)
        ),
    )
    assert not out.startswith("Error:")
    assert transport.last.path == "/order-estimation-tasks"


async def test_order_items_that_are_not_objects_are_reported_not_raised(transport):
    """A caller who sends bare IDs must get a sentence, not a traceback.

    `items_json="[1, 2, 3]"` parses as JSON and is a non-empty list, so the
    existing shape check passed it through to the core, where
    `_require_placements` calls `.get` on an int and the AttributeError escapes
    the tool's `try` -- `except ValueError` and `except PrintfulError` catch
    neither it nor the `TypeError` the same input raises one layer deeper.
    """
    try:
        out = await orders.create_order(
            transport, CreateOrderInput(items_json="[1, 2, 3]", **_recipient())
        )
    except Exception as exc:  # noqa: BLE001 - must catch any escape to report it via pytest.fail
        pytest.fail(
            f"create_order raised {type(exc).__name__}: {exc} instead of returning a readable error"
        )
    assert out.startswith("Error:")
    assert "must be a JSON object" in out
    assert transport.sent == [], "nothing may be sent for an input this malformed"


async def test_an_estimate_names_the_bad_items_instead_of_leaking_dict_internals(transport):
    """The old answer told the caller about a dictionary update sequence.

    `create_estimation_task` reaches `dict(item)` in the core, which for a list
    of strings raises ValueError("dictionary update sequence element #0 has
    length 1; 2 is required"). That was caught and returned, so the tool obeyed
    the return-don't-raise invariant while telling the caller nothing they
    could act on. The element-type check pre-empts it; the `except ValueError`
    stays for the core's own item validation.
    """
    try:
        out = await orders.create_estimation_task(
            transport, CreateEstimationTaskInput(recipient_country_code="US", items_json='["ab"]')
        )
    except Exception as exc:  # noqa: BLE001 - must catch any escape to report it via pytest.fail
        pytest.fail(
            f"create_estimation_task raised {type(exc).__name__}: {exc} "
            "instead of returning a readable error"
        )
    assert "must be a JSON object" in out
    assert "dictionary update sequence" not in out
    assert transport.sent == []
