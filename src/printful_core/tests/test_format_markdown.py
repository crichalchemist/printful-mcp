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


def test_a_product_list_page_reports_the_total_not_just_what_it_shows():
    """A page of 1 out of 239 must not read as 1 product existing, and the
    per-row techniques are what tells a caller whether a product supports
    the print method they need before they fetch its full detail.
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
    """
    out = markdown.tax({"required": True, "rate": 0.0825, "shipping_taxable": True})
    assert "**Tax required:** yes" in out
    assert "0.0825" in out
    assert "**Shipping taxable:** yes" in out
