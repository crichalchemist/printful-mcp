import pytest

from printful_core.endpoints import files, mockups, stores, sync


class TestMockups:
    def test_create_task_path_and_payload(self):
        req = mockups.create_task(71, [4012], "https://x/a.png")
        assert req.method == "POST"
        assert req.path == "/mockup-tasks"
        product = req.json["products"][0]
        assert product["catalog_product_id"] == 71
        assert product["catalog_variant_ids"] == [4012]
        assert product["placements"][0]["layers"][0]["url"] == "https://x/a.png"

    def test_create_task_includes_style_ids_when_given(self):
        req = mockups.create_task(71, [4012], "https://x/a.png", style_ids=[5, 6])
        assert req.json["products"][0]["mockup_style_ids"] == [5, 6]

    def test_create_task_rejects_empty_variants(self):
        with pytest.raises(ValueError, match="variant ID"):
            mockups.create_task(71, [], "https://x/a.png")

    def test_create_task_rejects_missing_image(self):
        with pytest.raises(ValueError, match="image URL"):
            mockups.create_task(71, [4012], "")

    def test_get_task_uses_id_param(self):
        assert mockups.get_task("t1").params == {"id": "t1"}

    def test_styles_and_templates_paths(self):
        assert mockups.list_styles(71).path == "/catalog-products/71/mockup-styles"
        assert mockups.list_templates(71).path == "/catalog-products/71/mockup-templates"


class TestFiles:
    def test_add_file_payload(self):
        req = files.add_file("https://x/a.png", filename="a.png")
        assert req.method == "POST"
        assert req.path == "/files"
        assert req.json == {"url": "https://x/a.png", "visible": True, "filename": "a.png"}

    def test_add_file_rejects_empty_url(self):
        with pytest.raises(ValueError, match="URL is required"):
            files.add_file("")

    def test_get_file_path(self):
        assert files.get_file(5).path == "/files/5"


class TestStores:
    def test_list_path(self):
        req = stores.list_stores()
        assert req.path == "/stores"
        assert req.version == "v2"

    def test_statistics_path_and_params(self):
        req = stores.get_statistics(1135966, "2026-01-01", "2026-03-01")
        assert req.path == "/stores/1135966/statistics"
        assert req.params["date_from"] == "2026-01-01"
        assert req.params["date_to"] == "2026-03-01"
        assert req.params["report_types"] == "sales_and_costs,profit"
        assert "currency" not in req.params

    def test_templates_use_v1(self):
        req = stores.list_templates()
        assert req.version == "v1"
        assert req.path == "/product-templates"


class TestSync:
    def test_list_uses_v1(self):
        req = sync.list_products()
        assert req.version == "v1"
        assert req.path == "/store/products"

    def test_get_uses_v1(self):
        req = sync.get_product(9)
        assert req.version == "v1"
        assert req.path == "/store/products/9"
