"""What each renderer prints, asserted field by field.

A renderer defect is silent: `.get` with a default turns a wrong key into
'N/A' rather than an exception, so the tool returns valid markdown that is
missing the one value the caller needed. Only an assertion on the rendered
value catches it, which is why each test below asserts every field its
renderer prints rather than one of them.

These call the renderers directly. They are pure functions of a body; a
transport and an input model would add two boundaries to a test whose
subject is a string.
"""

from printful_core.format import markdown


def test_a_catalog_product_page_carries_every_fact_a_buyer_needs():
    """`printful_get_product` is the only tool that shows techniques,
    placements and the discontinued flag together. A caller who cannot see
    all of it might order a technique the product no longer supports, or
    miss that it is discontinued at all.
    """
    out = markdown.product(
        {
            "id": 71,
            "name": "Unisex Tee",
            "type": "T-SHIRT",
            "brand": "Bella+Canvas",
            "variant_count": 100,
            "description": "A soft cotton tee.",
            "is_discontinued": True,
            "techniques": [
                {"key": "dtg", "display_name": "Direct to Garment", "is_default": True},
                {"key": "emb", "display_name": "Embroidery", "is_default": False},
            ],
            "placements": [
                {"placement": "front", "technique": "dtg"},
                {"placement": "back", "technique": "emb"},
            ],
        }
    )
    assert "# Unisex Tee" in out
    assert "**ID:** 71" in out
    assert "**Type:** T-SHIRT" in out
    assert "**Brand:** Bella+Canvas" in out
    assert "**Variants:** 100" in out
    assert "**Status:** Discontinued" in out
    assert "A soft cotton tee." in out
    assert "**Direct to Garment** (dtg) (default)" in out
    assert "**Embroidery** (emb)" in out
    assert "front - dtg" in out
    assert "back - emb" in out

    available = markdown.product({"id": 72, "name": "Available Tee"})
    assert "**Status:** Available" in available


def test_a_product_with_many_placements_says_how_many_it_is_not_showing():
    """`product` lists only the first five placements. Without the overflow
    line a caller reads five placements as all five that exist, and orders
    against a product whose remaining options they never saw.
    """
    body = {
        "id": 71,
        "name": "Tee",
        "placements": [{"placement": f"p{i}", "technique": "dtg"} for i in range(7)],
    }
    out = markdown.product(body)
    assert "_(and 2 more)_" in out
    assert "## Placements (7 available)" in out
    assert "p4 - dtg" in out
    assert "p5" not in out


def test_a_country_with_many_states_says_how_many_it_is_not_showing():
    """`countries` lists only the first three states per country. A caller
    shipping to the fourth needs to know it exists; three states with no
    overflow line reads as a country with three states.
    """
    out = markdown.countries(
        {
            "data": [
                {
                    "name": "United States",
                    "code": "US",
                    "states": [{"name": f"State{i}", "code": f"S{i}"} for i in range(5)],
                }
            ]
        }
    )
    assert "_(and 2 more)_" in out
    assert "**States:** 5 available" in out
    assert "State2 (S2)" in out
    assert "State3" not in out


def test_a_product_list_page_reports_the_total_not_just_what_it_shows():
    """A page of 1 out of 239 must not read as 1 product existing, and a
    page of 1 must not read as 239 products showing either -- the shown
    count and the grand total are two different numbers on this line, and
    collapsing them either way is a carry-over accounting bug.
    """
    out = markdown.products(
        {
            "data": [
                {
                    "id": 1,
                    "name": "Tee",
                    "type": "T-SHIRT",
                    "variant_count": 5,
                    "techniques": [{"key": "dtg"}, {"key": "emb"}],
                },
            ],
            "paging": {"total": 239, "offset": 10, "limit": 50},
        }
    )
    assert "239 total" in out
    assert "Showing 1 products" in out
    assert "offset: 10" in out
    assert "limit: 50" in out
    assert "## Tee" in out
    assert "**ID:** 1" in out
    assert "**Type:** T-SHIRT" in out
    assert "**Variants:** 5" in out
    assert "**Techniques:** dtg, emb" in out


def test_a_variant_row_carries_the_size_and_color_a_buyer_picks_by():
    """The variants response does not repeat the product it belongs to, so
    the caller supplies `product_id` for the heading; the row itself is
    useless for ordering without size, color and color_code.
    """
    out = markdown.variants(
        {
            "data": [
                {
                    "id": 4011,
                    "name": "Tee / S / Black",
                    "size": "S",
                    "color": "Black",
                    "color_code": "#000000",
                }
            ],
            "paging": {"total": 42},
        },
        product_id=71,
    )
    assert "# Variants for Product 71" in out
    assert "Total variants: 42" in out
    assert "## Tee / S / Black" in out
    assert "**Variant ID:** 4011" in out
    assert "**Size:** S" in out
    assert "**Color:** Black (#000000)" in out


def test_a_variant_page_past_the_end_still_names_its_product_and_the_total():
    """An empty page is an ordinary API response, not an error.

    `variants` takes `product_id` as an argument because the body does not
    carry it, so the heading is the only thing telling a caller which product
    came back empty. `total` matters most here: a page past the end shows no
    rows while 42 variants exist, and a caller that reads only the rows
    concludes the product has none.
    """
    out = markdown.variants({"data": [], "paging": {"total": 42}}, product_id=71)
    assert "# Variants for Product 71" in out
    assert "Total variants: 42" in out
    assert "Showing 0 variants" in out


def test_variant_pricing_keeps_every_line_tied_to_its_currency():
    """A bare number is unusable when the account bills in something else,
    and this renderer prints two separate price lists (base technique
    prices and additional placement prices) that both need it.
    """
    out = markdown.variant_prices(
        {
            "data": {
                "currency": "EUR",
                "variant": {
                    "techniques": [{"technique_display_name": "Embroidery", "price": "3.50"}]
                },
                "product": {"placements": [{"title": "Back print", "price": "5.95"}]},
            }
        },
        variant_id=4011,
    )
    assert "# Pricing for Variant 4011" in out
    assert "**Currency:** EUR" in out
    assert "**Embroidery:** 3.50 EUR" in out
    assert "**Back print:** 5.95 EUR" in out


def test_availability_ties_stock_to_the_technique_and_region_that_has_it():
    """A variant can be in stock for one technique in one region and out in
    another; collapsing any of catalog_variant_id/technique/region loses the
    distinction a buyer needs before placing an order.
    """
    out = markdown.availability(
        {
            "data": [
                {
                    "catalog_variant_id": 4011,
                    "techniques": [
                        {
                            "technique": "dtg",
                            "selling_regions": [{"name": "Europe", "availability": "in_stock"}],
                        }
                    ],
                }
            ],
        },
        product_id=71,
    )
    assert "# Availability for Product 71" in out
    assert "## Variant 4011" in out
    assert "### dtg" in out
    assert "**Europe:** in_stock" in out


def test_a_category_row_carries_the_id_a_caller_drills_into():
    """`printful_list_categories` is how a caller finds the id that
    `printful_get_category` needs, and a nested category needs its parent_id
    for a caller to place it in the tree. Rename either key and the row goes
    blank or the tree link vanishes -- with no error.
    """
    out = markdown.categories(
        {
            "data": [
                {"id": 24, "title": "Men's clothing", "parent_id": 0},
                {"id": 25, "title": "T-shirts", "parent_id": 24},
            ],
            "paging": {"total": 2},
        }
    )
    assert "2 total" in out
    assert "Showing 2 categories" in out
    assert "Men's clothing" in out
    assert "ID 24" in out
    assert "T-shirts" in out
    assert "ID 25" in out
    assert "(parent: 24)" in out


def test_a_category_detail_carries_its_parent_and_image_for_navigation():
    """`printful_get_category` is where a caller checks the parent id it
    already has and picks up an image url it did not. Either going missing
    reads as a category with no parent or no picture, not as a bug.
    """
    out = markdown.category(
        {"data": {"id": 25, "title": "T-shirts", "parent_id": 24, "image_url": "https://x/cat.png"}}
    )
    assert "# T-shirts" in out
    assert "**ID:** 25" in out
    assert "**Parent ID:** 24" in out
    assert "**Image:** https://x/cat.png" in out


def test_a_size_guide_leaf_value_is_the_number_a_buyer_measures_against():
    """`size_tables[].measurements[].values[]` nests three deep, and the
    leaf is the only thing a buyer actually reads -- a range for one size
    entry and a single value for another, both under one measurement type,
    both under one table.
    """
    out = markdown.size_guide(
        {
            "data": {
                "unit": "inches",
                "size_tables": [
                    {
                        "type": "Body measurements",
                        "description": "Measured flat, laid out.",
                        "measurements": [
                            {
                                "type_label": "Chest width",
                                "values": [
                                    {"size": "S", "min_value": "17", "max_value": "18"},
                                    {"size": "M", "value": "19"},
                                ],
                            }
                        ],
                    }
                ],
            }
        },
        product_id=71,
    )
    assert "# Size Guide for Product 71" in out
    assert "**Unit:** inches" in out
    assert "## Body measurements" in out
    assert "Measured flat, laid out." in out
    assert "**Chest width**" in out
    assert "S: 17-18" in out
    assert "M: 19" in out


def test_a_shipping_rate_reports_customs_risk_per_shipment_not_just_price():
    """A rate that is cheap but triggers a customs fee at the border is not
    the same offer as one that does not; both shipments under one method
    need their own departure country and customs flag.
    """
    out = markdown.rates(
        {
            "data": [
                {
                    "shipping_method_name": "Flat Rate",
                    "rate": "4.95",
                    "currency": "USD",
                    "min_delivery_days": 4,
                    "max_delivery_days": 6,
                    "min_delivery_date": "2026-09-20",
                    "max_delivery_date": "2026-09-22",
                    "shipments": [
                        {"customs_fees_possible": True, "departure_country": "US"},
                        {"customs_fees_possible": False, "departure_country": "DE"},
                    ],
                }
            ],
        }
    )
    assert "Found 1 shipping options" in out
    assert "## Flat Rate" in out
    assert "**Rate:** 4.95 USD" in out
    assert "4-6 days" in out
    assert "2026-09-20 to 2026-09-22" in out
    assert "From US - Customs fees possible: Yes" in out
    assert "From DE - Customs fees possible: No" in out


def test_a_country_row_surfaces_the_state_codes_shipping_needs():
    """A destination with states needs the state name and code a caller
    passes to shipping/tax calls; a destination without states must not
    print a states line it does not have.
    """
    out = markdown.countries(
        {
            "data": [
                {
                    "name": "United States",
                    "code": "US",
                    "states": [{"name": "California", "code": "CA"}],
                },
                {"name": "Germany", "code": "DE"},
            ],
        }
    )
    assert "# Available Countries (2 total)" in out
    assert "## United States (US)" in out
    assert "**States:** 1 available" in out
    assert "California (CA)" in out
    assert "## Germany (DE)" in out
    assert out.count("**States:**") == 1


def test_a_tax_answer_distinguishes_zero_from_not_required():
    """ "Tax required: no" and "Rate: 0" mean different things to a seller.

    `required` is a boolean the renderer turns into yes/no, and `rate` is a
    number that can legitimately be zero. A renderer reading the wrong key
    gets a falsy default and prints "no" for a destination that does charge
    tax, which is a wrong answer shaped like a right one.

    `/tax/rates` is a v1 endpoint (`endpoints/shipping.py`), and
    `transport._normalize` unwraps its `result` envelope before
    `tools/shipping.py` ever calls this renderer -- so the body
    `printful_calculate_tax` actually passes is bare, not `{"data": ...}`.
    That bare case is the production path and is asserted first. `tax` also
    accepts an enveloped body defensively -- it is the only one of these
    eleven renderers with a both-shapes guard, because it is the only v1
    endpoint among them -- and the enveloped case below pins that branch so
    a future edit cannot delete it silently, even though production never
    sends that shape.
    """
    out = markdown.tax({"required": True, "rate": 0.0825, "shipping_taxable": True})
    assert "**Tax required:** yes" in out
    assert "0.0825" in out
    assert "**Shipping taxable:** yes" in out

    not_required = markdown.tax({"required": False, "rate": 0.0825, "shipping_taxable": False})
    assert "**Tax required:** no" in not_required
    assert "**Shipping taxable:** no" in not_required

    enveloped = markdown.tax({"data": {"required": True, "rate": 0.0825, "shipping_taxable": True}})
    assert "**Tax required:** yes" in enveloped
    assert "0.0825" in enveloped
    assert "**Shipping taxable:** yes" in enveloped


def test_a_confirmed_order_reports_the_id_the_caller_must_quote():
    """printful_confirm_order charges the account, and its output is the
    caller's receipt. The id is the only handle on that charge -- a renamed
    key renders 'unknown' and the caller has been billed for an order they
    cannot look up.

    `calculation_status` lives under `costs`, not at the body's top level --
    the brief's own worked example places it at the top, and the renderer
    never reads it from there (verified by running that exact fixture: the
    'done' branch never fires and the cost lines never print). This fixture
    nests it correctly so the 'done' branch's five cost lines actually render.
    """
    out = markdown.order(
        {
            "id": 98765,
            "status": "pending",
            "external_id": "ext-1",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-02",
            "recipient": {
                "name": "A Buyer",
                "address1": "1 Main St",
                "city": "SF",
                "state_code": "CA",
                "zip": "94107",
                "country_name": "United States",
                "country_code": "US",
            },
            "costs": {
                "calculation_status": "done",
                "currency": "USD",
                "subtotal": 20.0,
                "shipping": 5.0,
                "tax": 1.5,
                "total": 26.5,
            },
            "order_items": [
                {
                    "id": 4501,
                    "name": "Tee",
                    "catalog_variant_id": 4012,
                    "quantity": 1,
                    "price": 20.0,
                    "currency": "USD",
                }
            ],
        }
    )
    assert "# Order 98765" in out
    assert "**Status:** pending" in out
    assert "**External ID:** ext-1" in out
    assert "**Created:** 2026-01-01" in out
    assert "**Updated:** 2026-01-02" in out
    assert "**Name:** A Buyer" in out
    assert "**Address:** 1 Main St" in out
    assert "**City:** SF, CA 94107" in out
    assert "**Country:** United States (US)" in out
    assert "**Currency:** USD" in out
    assert "**Subtotal:** 20.0" in out
    assert "**Shipping:** 5.0" in out
    assert "**Tax:** 1.5" in out
    assert "**Total:** 26.5" in out
    assert "## Order Items (1)" in out
    assert "- **Item 4501**: Tee" in out
    assert "Variant: 4012" in out
    assert "Quantity: 1" in out
    assert "Price: 20.0 USD" in out


def test_an_empty_order_body_degrades_without_claiming_a_wrong_id():
    """A 204 or empty 2xx reaches this renderer as {}. It must not invent an
    id: 'unknown' is honest, a stale or defaulted number is not -- and it
    must not render a Recipient/Costs/Order Items section that implies data
    the response never carried.
    """
    out = markdown.order({})
    assert "# Order unknown" in out
    assert "**Status:** unknown" in out
    assert "**External ID:** N/A" in out
    assert "**Created:** N/A" in out
    assert "**Updated:** N/A" in out
    assert "## Recipient" not in out
    assert "## Costs" not in out
    assert "## Order Items" not in out
    assert isinstance(out, str)


def test_an_order_with_costs_still_calculating_reports_the_status_not_stale_totals():
    """Costs are calculated asynchronously. A caller polling mid-calculation
    must see why totals are missing, not a phantom subtotal borrowed from the
    'done' branch's defaults -- both branches print a line labelled
    '**Status:**' under '## Costs', so a rename can silently swap one for
    the other without either assertion failing on its own.
    """
    out = markdown.order(
        {
            "id": 222,
            "status": "draft",
            "costs": {"calculation_status": "calculating"},
        }
    )
    assert "**Status:** calculating" in out
    assert "**Status:** draft" in out
    assert "**Subtotal:**" not in out
    assert "**Total:**" not in out


def test_an_orders_page_reports_the_total_not_just_what_it_shows():
    """A page of 1 out of 87 must not read as 1 order existing -- the same
    carry-over accounting bug `products` (this renderer's catalog sibling)
    had to guard against.
    """
    out = markdown.orders(
        {
            "data": [
                {
                    "id": 555,
                    "status": "fulfilled",
                    "external_id": "ext-77",
                    "created_at": "2026-02-01",
                    "costs": {"total": 42.5, "currency": "USD"},
                    "order_items": [{"id": 1}, {"id": 2}],
                }
            ],
            "paging": {"total": 87, "offset": 5, "limit": 50},
        }
    )
    assert "87 total" in out
    assert "Showing 1 orders" in out
    assert "offset: 5" in out
    assert "limit: 50" in out
    assert "## Order 555" in out
    assert "**Status:** fulfilled" in out
    assert "**External ID:** ext-77" in out
    assert "**Total:** 42.5 USD" in out
    assert "**Items:** 2" in out
    assert "**Created:** 2026-02-01" in out


def test_order_items_page_names_the_order_it_belongs_to():
    """`printful_list_order_items` doesn't repeat the order id on each row --
    the caller supplies it for the heading -- so a wrong row key silently
    drops the one thing that tells someone what they are about to ship.
    """
    out = markdown.order_items(
        {
            "data": [
                {
                    "id": 9001,
                    "name": "Hoodie",
                    "catalog_variant_id": 4013,
                    "quantity": 3,
                    "price": 35.0,
                    "currency": "EUR",
                }
            ]
        },
        order_id="ORD-1",
    )
    assert "# Items on Order ORD-1 (1)" in out
    assert "## Item 9001" in out
    assert "**Name:** Hoodie" in out
    assert "**Variant:** 4013" in out
    assert "**Quantity:** 3" in out
    assert "**Price:** 35.0 EUR" in out


def test_a_shipment_row_carries_the_tracking_a_buyer_follows():
    """A shipped order with no tracking number or URL leaves a buyer unable
    to find their package; this renderer is the only place those two values
    surface together with the carrier and service that sent them.
    """
    out = markdown.shipments(
        {
            "data": [
                {
                    "id": 701,
                    "carrier": "USPS",
                    "service": "Priority",
                    "tracking_number": "9400abc123",
                    "tracking_url": "https://track.example/9400abc123",
                    "shipped_at": "2026-03-01",
                }
            ]
        },
        order_id="ORD-2",
    )
    assert "# Shipments for Order ORD-2 (1)" in out
    assert "## Shipment 701" in out
    assert "**Carrier:** USPS" in out
    assert "**Service:** Priority" in out
    assert "**Tracking number:** 9400abc123" in out
    assert "**Tracking URL:** https://track.example/9400abc123" in out
    assert "**Shipped at:** 2026-03-01" in out


def test_an_order_with_no_shipments_yet_says_so_instead_of_an_empty_list():
    """Before fulfillment, `data` is genuinely empty -- a bare '(0)' heading
    would read as a bug or a lost shipment rather than 'not shipped yet'.
    """
    out = markdown.shipments({"data": []}, order_id="ORD-3")
    assert "No shipments yet. Shipments appear once the order is fulfilled." in out
    assert "# Shipments for Order ORD-3" in out


def test_a_pending_estimate_tells_the_caller_to_poll_again():
    """A pending estimate has no costs yet -- printing N/A costs instead of
    saying 'still calculating' would read as a $0 order.
    """
    out = markdown.estimate({}, status="pending")
    assert "still being calculated" in out
    assert "printful_get_estimation_task" in out
    assert "**Status:** pending" in out


def test_a_failed_estimate_lists_the_reasons_not_just_that_it_failed():
    """A caller cannot fix an estimate that failed for an unstated reason --
    the reason strings are the only actionable content in this branch, and
    an empty list must still say something rather than nothing.
    """
    out = markdown.estimate(
        {"failure_reasons": ["Unsupported destination", "Missing weight"]},
        status="failed",
    )
    assert "- Unsupported destination" in out
    assert "- Missing weight" in out
    assert "**Status:** failed" in out

    no_reasons = markdown.estimate({"failure_reasons": []}, status="failed")
    assert "- No reason given." in no_reasons


def test_a_completed_estimate_reports_every_cost_line_in_its_currency():
    """The four cost lines only mean something tied to a currency -- a
    caller comparing this estimate against a live order needs all five
    numbers together to catch a shipping-fee surprise before confirming.
    """
    out = markdown.estimate(
        {
            "costs": {
                "currency": "GBP",
                "subtotal": 18.0,
                "shipping": 4.25,
                "tax": 0.9,
                "total": 23.15,
            }
        },
        status="completed",
    )
    assert "**Total:** 23.15" in out
    assert "**Status:** completed" in out
    assert "**Currency:** GBP" in out
    assert "**Subtotal:** 18.0" in out
    assert "**Shipping:** 4.25" in out
    assert "**Tax:** 0.9" in out


def test_a_completed_mockup_task_hands_back_the_url_per_variant_and_placement():
    """Every mockup is scoped to one catalog variant and one placement --
    collapsing either key merges unrelated mockup URLs under the wrong
    variant heading, which is which image belongs to which SKU.
    """
    out = markdown.mockup_task(
        {
            "id": "task-1",
            "status": "completed",
            "catalog_variant_mockups": [
                {
                    "catalog_variant_id": 4012,
                    "mockups": [
                        {
                            "placement": "front",
                            "style_id": 7,
                            "mockup_url": "https://mockups.example/front.png",
                            "display_name": "Front view",
                        }
                    ],
                }
            ],
        }
    )
    assert "https://mockups.example/front.png" in out
    assert "# Mockup Task task-1" in out
    assert "## Generated Mockups (1 variants)" in out
    assert "### Variant 4012" in out
    assert "**Front view** (front)" in out
    assert "Style ID: 7" in out
    assert "**Status:** completed" in out


def test_a_pending_mockup_task_tells_the_caller_to_check_back():
    """A caller polling `printful_get_mockup_task` too early must see
    'in progress', not a blank mockup list that reads as zero mockups ever
    coming.
    """
    out = markdown.mockup_task({"id": "task-2", "status": "pending"})
    assert "in progress" in out
    assert "**Status:** pending" in out


def test_a_failed_mockup_task_lists_why_not_just_that_it_failed():
    """A caller cannot retry sensibly without the reason -- 'failed' alone
    hides whether it was a bad file url or an unsupported placement.
    """
    out = markdown.mockup_task(
        {
            "id": "task-3",
            "status": "failed",
            "failure_reasons": [{"detail": "File could not be downloaded"}],
        }
    )
    assert "File could not be downloaded" in out
    assert "**Status:** failed" in out


def test_a_failed_mockup_task_with_no_reasons_skips_the_heading_entirely():
    """The API does not always say why. `failure_reasons` gates the
    `**Reasons:**` heading, and a heading with nothing under it reads as a
    rendering bug to a caller who then goes looking for the list that is not
    there. The failure itself must still be reported.
    """
    out = markdown.mockup_task({"id": "task-4", "status": "failed"})
    assert "**Reasons:**" not in out
    assert "\u274c Mockup generation failed." in out
    assert "**Status:** failed" in out


def test_a_mockup_style_row_carries_the_id_a_caller_requests_by():
    """`printful_create_mockup_task` takes style ids from this list --
    losing `id` here means a caller can name a style but not order it.
    """
    out = markdown.mockup_styles(
        {"data": [{"id": 101, "name": "Lifestyle", "placement": "front", "technique": "dtg"}]},
        product_id=71,
    )
    assert "# Mockup Styles for Product 71 (1)" in out
    assert "## Lifestyle — ID 101" in out
    assert "**Placement:** front" in out
    assert "**Technique:** dtg" in out


def test_an_added_file_still_processing_reports_status_without_stale_dimensions():
    """`printful_add_file` returns immediately; the file may still be
    processing. A caller must see 'waiting' and not a dimensions/size block
    that implies the upload already finished.
    """
    out = markdown.file_added({"id": 601, "status": "waiting", "filename": "logo.png"})
    assert "**Status:** waiting" in out
    assert "⏳ File is being processed. Check status with printful_get_file." in out
    assert "**File ID:** 601" in out
    assert "**Filename:** logo.png" in out
    assert "**Dimensions:**" not in out


def test_an_added_file_that_finished_processing_carries_the_dimensions_and_preview():
    """Once `status` is 'ok', the dimensions/dpi/size/preview_url block is
    the only place a caller learns whether the upload the API accepted is
    actually usable for printing -- a renamed key here degrades silently to
    'None' rather than raising.
    """
    out = markdown.file_added(
        {
            "id": 602,
            "status": "ok",
            "filename": "design.png",
            "url": "https://example.com/design.png",
            "width": 4500,
            "height": 5400,
            "dpi": 300,
            "size": 204800,
            "preview_url": "https://example.com/preview.png",
        }
    )
    assert "**Filename:** design.png" in out
    assert "**File ID:** 602" in out
    assert "**Status:** ok" in out
    assert "**Original URL:** https://example.com/design.png" in out
    assert "**Dimensions:** 4500x5400px" in out
    assert "**DPI:** 300" in out
    assert "**Size:** 204800 bytes" in out
    assert "**Preview:** https://example.com/preview.png" in out


def test_a_finished_file_detail_carries_the_hash_a_caller_verifies_integrity_with():
    """`printful_get_file` is the only tool that surfaces `hash` -- a caller
    comparing a re-uploaded file against the library copy has no other way
    to tell them apart, and it sits alongside dimensions/size/urls that a
    print job also depends on.
    """
    out = markdown.file_detail(
        {
            "id": 701,
            "status": "ok",
            "filename": "logo.svg",
            "mime_type": "image/svg+xml",
            "created": "2026-01-05",
            "width": 800,
            "height": 600,
            "dpi": 150,
            "size": 20480,
            "hash": "abc123hash",
            "url": "https://example.com/logo.svg",
            "thumbnail_url": "https://example.com/logo-thumb.svg",
            "preview_url": "https://example.com/logo-preview.svg",
        }
    )
    assert "**Hash:** abc123hash" in out
    assert "# File 701" in out
    assert "**Status:** ok" in out
    assert "**Filename:** logo.svg" in out
    assert "**MIME Type:** image/svg+xml" in out
    assert "**Created:** 2026-01-05" in out
    assert "**Dimensions:** 800x600px" in out
    assert "**DPI:** 150" in out
    assert "**Size:** 20480 bytes" in out
    assert "**Original:** https://example.com/logo.svg" in out
    assert "**Thumbnail:** https://example.com/logo-thumb.svg" in out
    assert "**Preview:** https://example.com/logo-preview.svg" in out


def test_a_file_still_processing_says_so_instead_of_a_blank_detail_block():
    """A caller polling `printful_get_file` before it finishes must see
    'still being processed', not a Details/URLs block with every value
    rendering None.
    """
    out = markdown.file_detail({"id": 702, "status": "waiting", "filename": "logo.svg"})
    assert "**Status:** waiting" in out
    assert "⏳ File is still being processed." in out
    assert "## File Details" not in out


def test_a_failed_file_reports_the_failure_not_a_silent_n_a_block():
    """A caller cannot retry a file upload sensibly if 'failed' renders
    indistinguishably from 'waiting' or from a successful file with blank
    fields -- this is the only branch that says the file will never be
    usable.
    """
    out = markdown.file_detail({"id": 703, "status": "failed", "filename": "logo.svg"})
    assert "**Status:** failed" in out
    assert "❌ File processing failed. The file may be invalid or inaccessible." in out
    assert "## File Details" not in out


def test_a_store_row_carries_the_id_and_type_a_caller_switches_context_by():
    """`printful_get_store_stats` and the sync-product tools all take a
    store id that only this renderer supplies -- a renamed `id` or `type`
    leaves a caller unable to tell two connected stores apart.
    """
    out = markdown.stores(
        {
            "data": [
                {"id": 501, "name": "My Threads Shop", "type": "manual"},
                {"id": 502, "name": "Etsy Connect", "type": "etsy"},
            ]
        }
    )
    assert "**ID:** 501" in out
    assert "## My Threads Shop" in out
    assert "**Type:** manual" in out
    assert "**ID:** 502" in out
    assert "## Etsy Connect" in out
    assert "**Type:** etsy" in out
    assert "# Stores (2 total)" in out


def test_a_store_with_no_activity_shows_no_metric_sections_at_all():
    """Each of the four metric sections is gated on its own key. A brand-new
    store returns none of them, and a heading with no figure under it reads
    as a rendering fault to a seller who then goes looking for numbers that
    were never sent. The requested window must still print, because that is
    the only thing saying which period came back empty.
    """
    out = markdown.store_statistics(
        {"data": {"store_id": 9001, "currency": "USD"}},
        date_from="2026-09-01",
        date_to="2026-09-16",
    )
    assert "## Profit" not in out
    assert "## Total Paid Orders" not in out
    assert "## Printful Costs" not in out
    assert "## Average Fulfillment Time" not in out
    assert "# Store Statistics (2026-09-01 to 2026-09-16)" in out
    assert "**Store ID:** 9001" in out


def test_a_sync_product_with_no_variants_omits_the_variants_section():
    """`sync_variants` gates the whole section. A sync product can exist with
    none -- an empty '## Sync Variants (0)' heading tells a caller variants
    were fetched and found empty, when in fact none were returned at all.
    """
    out = markdown.sync_product(
        {"sync_product": {"id": 8001, "name": "Tee", "external_id": "ext-1"}}
    )
    assert "## Sync Variants" not in out
    assert "# Tee" in out
    assert "**Sync Product ID:** 8001" in out
    assert "**External ID:** ext-1" in out


def test_store_statistics_header_carries_the_requested_window_not_the_body():
    """`store_statistics` takes `date_from`/`date_to` as arguments because
    the response body does not carry the range back -- the header must
    print what was *asked for*, and each of the four metric sections needs
    its own value tied to its own percentage change, not a neighbor's.
    """
    out = markdown.store_statistics(
        {
            "data": {
                "store_id": 9001,
                "currency": "GBP",
                "profit": {"value": 120.5, "relative_difference": "+12%"},
                "total_paid_orders": {"value": 34, "relative_difference": "-3%"},
                "printful_costs": {"value": 80.25, "relative_difference": "+5%"},
                "average_fulfillment_time": {"value": 2.4, "relative_difference": "-0.5%"},
            }
        },
        date_from="2026-08-01",
        date_to="2026-08-31",
    )
    assert "# Store Statistics (2026-08-01 to 2026-08-31)" in out
    assert "**Store ID:** 9001" in out
    assert "**Currency:** GBP" in out
    assert "**Value:** 120.5 GBP" in out
    assert "**Change:** +12%" in out
    assert "**Count:** 34" in out
    assert "**Change:** -3%" in out
    assert "**Value:** 80.25 GBP" in out
    assert "**Change:** +5%" in out
    assert "**Days:** 2.4" in out
    assert "**Change:** -0.5%" in out


def test_a_template_row_shows_the_product_id_not_a_v2_field_name():
    """This renderer shipped reading `catalog_product_id`; the API sends
    `product_id`, so every row printed 'N/A' and nothing failed. The v1
    body also arrives as `items`, not the v2 `data` envelope -- reading
    `data` renders 'Showing 0 templates' for a store that has templates.

    `paging.total` is deliberately 5 against a single row: `paging.get`
    falls back to `len(rows)` (1) when the key is missing, and a fixture
    where `total` already equals `len(rows)` cannot tell a live `total`
    read from that silent fallback -- a mutation sweep against the first
    draft of this fixture (`total: 1`) proved exactly that (both `paging`
    and `total` survived the whole-file sweep untouched).
    """
    out = markdown.store_templates(
        {
            "items": [
                {"id": 77, "title": "Summer Tee", "product_id": 71, "created_at": "2026-01-01"}
            ],
            "paging": {"total": 5},
        }
    )
    assert "5 total" in out
    assert "71" in out
    assert "Summer Tee" in out
    assert "77" in out
    assert "2026-01-01" in out
    assert "Showing 1 templates" in out


def test_a_bare_list_of_templates_still_renders():
    """v1 hands some collections back as the list itself. `.get` on a list
    raises AttributeError, which is not a PrintfulError and escapes the tool
    as a traceback where an MCP client expects a string.
    """
    out = markdown.store_templates(
        [{"id": 77, "title": "Summer Tee", "product_id": 71, "created_at": "2026-01-01"}]
    )
    assert "Summer Tee" in out
    assert "71" in out
    assert "77" in out


def test_store_templates_with_a_null_v1_result_renders_instead_of_raising():
    """`{"code": 200, "result": null}` unwraps to `None`. `isinstance(None,
    list)` is False, so the un-guarded renderer fell into the `else` branch
    and called `.get` on `None`, raising `AttributeError` where an MCP
    client expects a string.
    """
    out = markdown.store_templates(None)
    assert isinstance(out, str)
    assert "# Product Templates (0 total)" in out
    assert "Showing 0 templates" in out


def test_a_sync_products_page_reports_shown_count_and_variant_totals():
    """`sync_products` is v1-only and its envelope key is `items`, not the
    v2 `data` this file's other list renderers read -- reading the wrong
    one renders '0 shown' for a store that has sync products.
    """
    out = markdown.sync_products(
        {
            "items": [
                {
                    "id": 8001,
                    "name": "Custom Mug",
                    "external_id": "ext-mug-1",
                    "sync_variants": [{"id": 1}, {"id": 2}, {"id": 3}],
                }
            ]
        }
    )
    assert "**Sync Product ID:** 8001" in out
    assert "## Custom Mug" in out
    assert "**External ID:** ext-mug-1" in out
    assert "**Sync Variants:** 3" in out
    assert "# Sync Products (1 shown)" in out


def test_a_bare_list_of_sync_products_still_renders():
    """The same bare-list shape `store_templates` documents can arrive
    here too; reading only `.get('items', [])` on a bare list raises
    AttributeError instead of rendering.
    """
    out = markdown.sync_products(
        [{"id": 8002, "name": "Custom Cap", "external_id": "ext-cap-1", "sync_variants": []}]
    )
    assert "**Sync Product ID:** 8002" in out
    assert "## Custom Cap" in out
    assert "**External ID:** ext-cap-1" in out
    assert "**Sync Variants:** 0" in out


def test_sync_products_with_a_null_v1_result_renders_instead_of_raising():
    """Symmetric with `store_templates`: a `result: null` v1 body must
    render '(0 shown)' rather than raise AttributeError on `None.get`.
    """
    out = markdown.sync_products(None)
    assert isinstance(out, str)
    assert "# Sync Products (0 shown)" in out


def test_a_sync_product_detail_carries_variant_pricing_and_currency():
    """`sync_product` takes the bare body, no envelope -- `sync_product`
    and `sync_variants` are its own top-level keys. A caller placing an
    order from `printful_get_sync_product` needs `variant_id` (the catalog
    variant to order) and `retail_price`/`currency` together, or they quote
    a price with no currency or order the wrong SKU.
    """
    out = markdown.sync_product(
        {
            "sync_product": {
                "id": 9001,
                "name": "Custom Hoodie",
                "external_id": "ext-hoodie-1",
                "thumbnail_url": "https://example.com/hoodie-thumb.png",
            },
            "sync_variants": [
                {
                    "id": 501,
                    "name": "Hoodie / M / Black",
                    "external_id": "ext-var-1",
                    "variant_id": 4099,
                    "retail_price": "29.99",
                    "currency": "USD",
                }
            ],
        }
    )
    assert "**Variant ID:** 4099" in out
    assert "**Retail Price:** 29.99 USD" in out
    assert "# Custom Hoodie" in out
    assert "**Sync Product ID:** 9001" in out
    assert "**External ID:** ext-hoodie-1" in out
    assert "**Thumbnail:** https://example.com/hoodie-thumb.png" in out
    assert "## Sync Variants (1)" in out
    assert "### Variant 501" in out
    assert "**Name:** Hoodie / M / Black" in out
    assert "**External ID:** ext-var-1" in out


def test_a_mockup_template_row_carries_the_print_area_a_design_must_fit():
    """A design that exceeds `print_area_width`/`height` gets rejected or
    cropped at generation time -- this is the only place those two numbers
    surface before a caller submits a mockup task.
    """
    out = markdown.mockup_templates(
        {
            "data": [
                {
                    "id": 55,
                    "placement": "back",
                    "technique": "embroidery",
                    "print_area_width": 12,
                    "print_area_height": 16,
                    "image_url": "https://mockups.example/template-55.png",
                }
            ]
        },
        product_id=71,
    )
    assert "# Mockup Templates for Product 71 (1)" in out
    assert "## Template 55" in out
    assert "**Placement:** back" in out
    assert "**Technique:** embroidery" in out
    assert "**Print area:** 12x16" in out
    assert "https://mockups.example/template-55.png" in out
