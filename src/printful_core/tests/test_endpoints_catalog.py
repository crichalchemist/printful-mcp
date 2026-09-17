from printful_core.endpoints import catalog


def test_list_products_path_and_defaults():
    req = catalog.list_products()
    assert req.method == "GET"
    assert req.path == "/catalog-products"
    assert req.params == {"limit": 20, "offset": 0}


def test_list_products_drops_unset_filters():
    req = catalog.list_products(limit=5, colors="black")
    assert req.params == {"limit": 5, "offset": 0, "colors": "black"}


def test_get_product_path():
    assert catalog.get_product(71).path == "/catalog-products/71"


def test_list_variants_path():
    assert catalog.list_variants(71).path == "/catalog-products/71/catalog-variants"


def test_variant_prices_path():
    assert catalog.get_variant_prices(4012).path == "/catalog-variants/4012/prices"


def test_availability_path():
    assert catalog.get_availability(71).path == "/catalog-products/71/availability"


def test_categories_path():
    assert catalog.list_categories().path == "/catalog-categories"


def test_category_path():
    assert catalog.get_category(24).path == "/catalog-categories/24"


def test_size_guide_path():
    assert catalog.get_size_guide(71).path == "/catalog-products/71/sizes"


def test_size_guide_unit_passed_through():
    assert catalog.get_size_guide(71, unit="cm").params == {"unit": "cm"}
