from printful_core.format import summary


class TestProducts:
    def test_empty(self):
        assert summary.products({})["count"] == 0

    def test_partial_payload_does_not_raise(self):
        out = summary.products({"data": [{"id": 1, "name": "Tee"}]})
        assert out["products"][0]["type"] is None
        assert out["products"][0]["techniques"] == ""

    def test_techniques_joined(self):
        out = summary.products(
            {"data": [{"id": 1, "name": "Tee", "techniques": [{"key": "dtg"}, {"key": "emb"}]}]}
        )
        assert out["products"][0]["techniques"] == "dtg,emb"


class TestRates:
    def test_live_keys(self):
        """Live rows are keyed shipping / shipping_method_name, not id / name."""
        row = summary.rates(
            {
                "data": [
                    {
                        "shipping": "STANDARD",
                        "shipping_method_name": "Flat Rate",
                        "rate": "4.95",
                        "currency": "USD",
                        "min_delivery_days": 4,
                        "max_delivery_days": 6,
                    }
                ]
            }
        )["rates"][0]
        assert row["id"] == "STANDARD"
        assert row["name"] == "Flat Rate"
        assert row["rate"] == "4.95"

    def test_falls_back_to_id_and_name(self):
        row = summary.rates({"data": [{"id": "X", "name": "Legacy", "rate": "1.00"}]})["rates"][0]
        assert row["id"] == "X"
        assert row["name"] == "Legacy"

    def test_empty(self):
        assert summary.rates({})["count"] == 0

    def test_live_keys_win_when_both_present(self):
        """A row carrying both shapes must resolve to the live keys, not the documented ones."""
        data = {
            "data": [
                {
                    "shipping": "LIVE",
                    "shipping_method_name": "LiveName",
                    "id": "DOCS",
                    "name": "DocsName",
                    "rate": "1.00",
                    "currency": "USD",
                }
            ]
        }
        row = summary.rates(data)["rates"][0]
        assert row["id"] == "LIVE"
        assert row["name"] == "LiveName"


class TestCountries:
    def test_counts_states(self):
        out = summary.countries(
            {"data": [{"code": "US", "name": "United States", "states": [1, 2]}]}
        )
        assert out["countries"][0]["states"] == 2

    def test_missing_states_key(self):
        assert summary.countries({"data": [{"code": "DE"}]})["countries"][0]["states"] == 0


class TestOrders:
    def test_missing_costs(self):
        out = summary.orders({"data": [{"id": 1, "status": "draft"}]})
        assert out["orders"][0]["total"] is None
        assert out["count"] == 1

    def test_does_not_mutate_input(self):
        import copy

        data = {"data": [{"id": 1, "status": "draft"}]}
        snapshot = copy.deepcopy(data)
        summary.orders(data)
        assert data == snapshot


class TestMockupUrls:
    def test_primary_and_extra(self):
        data = {
            "data": [
                {
                    "mockups": [
                        {"mockup_url": "https://x/1.jpg", "extra": [{"url": "https://x/2.jpg"}]}
                    ]
                }
            ]
        }
        assert summary.mockup_urls(data) == ["https://x/1.jpg", "https://x/2.jpg"]

    def test_empty_and_malformed(self):
        assert summary.mockup_urls({}) == []
        assert summary.mockup_urls({"data": ["junk"]}) == []


class TestVariantsAndStores:
    def test_variants_empty(self):
        assert summary.variants({})["count"] == 0

    def test_stores(self):
        out = summary.stores({"data": [{"id": 1, "name": "A", "type": "native"}]})
        assert out["stores"][0]["name"] == "A"
