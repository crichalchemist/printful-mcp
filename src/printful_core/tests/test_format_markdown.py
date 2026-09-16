"""The markdown renderers, exercised with no transport at all."""
from printful_core.format import markdown


def test_a_discontinued_product_says_so():
    """The status line is the one field a buyer acts on.

    `is_discontinued` is a boolean in the response and reads as neither word,
    so the renderer is what turns it into something a person can use.
    """
    out = markdown.product({
        "id": 71, "name": "Unisex Tee", "type": "T-SHIRT", "brand": "Bella",
        "variant_count": 100, "is_discontinued": True,
    })
    assert "**Status:** Discontinued" in out


def test_a_product_list_reports_the_total_not_the_page_size():
    """A page of 2 out of 239 must not read as 2 products existing."""
    out = markdown.products({
        "data": [{"id": 1, "name": "A", "type": "T", "variant_count": 3},
                 {"id": 2, "name": "B", "type": "T", "variant_count": 4}],
        "paging": {"total": 239, "offset": 0, "limit": 2},
    })
    assert "239 total" in out
    assert "Showing 2 products" in out


def test_variants_name_the_product_they_belong_to():
    """The variants response carries no product id, so the caller supplies it."""
    out = markdown.variants({"data": [], "paging": {"total": 0}}, product_id=71)
    assert "# Variants for Product 71" in out


def test_placement_prices_carry_the_response_currency():
    """A bare number is unusable when the account bills in something else."""
    out = markdown.variant_prices({"data": {
        "currency": "EUR",
        "product": {"placements": [{"title": "Back print", "price": "5.95"}]},
    }}, variant_id=4011)
    assert "5.95 EUR" in out
