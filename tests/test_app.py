import json
import tempfile
import unittest
from pathlib import Path

from app import create_app


class AppRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self.app = create_app(
            {
                "TESTING": True,
                "DATA_DIR": self.data_dir,
                "DISABLE_NETWORK": True,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_health_endpoint_reports_app_status(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("data", payload)

    def test_add_card_appends_to_game_file(self):
        response = self.client.post(
            "/api/add-card",
            data=json.dumps(
                {
                    "game": "MTG",
                    "card_line": "Lightning Bolt #150",
                    "finish": "foil",
                    "quantity": 2,
                    "buy_price": "1.25",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "added")
        self.assertEqual(
            (self.data_dir / "mtg_cards.txt").read_text(encoding="utf-8"),
            "2x Lightning Bolt #150 (Foil) | 1.25\n",
        )

    def test_add_card_rejects_duplicate_line(self):
        (self.data_dir / "ygo_cards.txt").write_text(
            "Dark Magician\n", encoding="utf-8"
        )

        response = self.client.post(
            "/api/add-card",
            json={"game": "YGO", "card_line": "Dark Magician"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "duplicate")

    def test_add_card_uses_legacy_collection_file_when_present(self):
        (self.data_dir / "my_cards.txt").write_text("Lightning Bolt #150\n", encoding="utf-8")

        response = self.client.post(
            "/api/add-card",
            json={"game": "YGO", "card_line": "Dark Magician"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (self.data_dir / "my_cards.txt").read_text(encoding="utf-8"),
            "Lightning Bolt #150\n[YGO] Dark Magician\n",
        )

    def test_dashboard_reads_legacy_cached_price_data(self):
        (self.data_dir / "my_cards.txt").write_text("Lightning Bolt #150\n", encoding="utf-8")
        (self.data_dir / "price_history.csv").write_text("2026-06-23,5.50\n", encoding="utf-8")
        (self.data_dir / "last_run_data.json").write_text(
            json.dumps(
                {
                    "MTG|Lightning Bolt #150": {
                        "data": {
                            "game": "MTG",
                            "name": "Lightning Bolt",
                            "set": "Core Set",
                            "price": "5.50",
                            "image": "",
                            "uri": "https://example.test/card",
                        },
                        "quantity": 1,
                        "price_str": "5.50",
                        "profit_loss": None,
                        "sort_val": 5.5,
                        "is_foil": False,
                        "card_key": "MTG|Lightning Bolt #150",
                    }
                }
            ),
            encoding="utf-8",
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Lightning Bolt", body)
        self.assertIn("$5.50", body)

    def test_dashboard_renders_wishlist_cache_images(self):
        (self.data_dir / "wishlist.txt").write_text(
            "Lightning Bolt (Foil) #150 | < 2.00\n",
            encoding="utf-8",
        )
        (self.data_dir / "wishlist_cache.json").write_text(
            json.dumps(
                {
                    "last_updated": "2026-06-23",
                    "items": [
                        {
                            "game": "MTG",
                            "card_line": "Lightning Bolt (Foil) #150",
                            "name": "Lightning Bolt",
                            "set": "Core Set",
                            "image": "https://example.test/lightning-bolt.jpg",
                            "uri": "https://example.test/lightning-bolt",
                            "current_price": 1.5,
                            "target_price": 2,
                            "target_label": "< 2.00",
                            "operator": "<",
                            "is_deal": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("https://example.test/lightning-bolt.jpg", body)
        self.assertIn("$1.50", body)
        self.assertIn("Deal", body)
        self.assertIn("wishlist-panel", body)

    def test_dashboard_shows_portfolio_snapshot(self):
        (self.data_dir / "my_cards.txt").write_text("Lightning Bolt #150\n", encoding="utf-8")
        (self.data_dir / "price_history.csv").write_text(
            "2026-06-22,100.00\n2026-06-23,125.25\n", encoding="utf-8"
        )
        (self.data_dir / "last_run_data.json").write_text(
            json.dumps(
                {
                    "MTG|Lightning Bolt #150": {
                        "data": {
                            "game": "MTG",
                            "name": "Lightning Bolt",
                            "set": "Core Set",
                            "price": "5.50",
                            "image": "",
                            "uri": "https://example.test/card",
                        },
                        "quantity": 1,
                        "price_str": "5.50",
                        "profit_loss": None,
                        "sort_val": 5.5,
                        "is_foil": False,
                        "card_key": "MTG|Lightning Bolt #150",
                    }
                }
            ),
            encoding="utf-8",
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("portfolio-snapshot", body)
        self.assertIn("+25.25", body)
        self.assertIn("Top Holding", body)

    def test_dashboard_has_mobile_viewport_and_status_region(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('name="viewport"', body)
        self.assertIn('class="status-strip"', body)
        self.assertIn('id="themeToggle"', body)

    def test_wishlist_targets_are_available_before_first_refresh(self):
        (self.data_dir / "wishlist.txt").write_text(
            "Lightning Bolt #150 | <= $2.00\n",
            encoding="utf-8",
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Target &lt;= $2.00", body)


if __name__ == "__main__":
    unittest.main()
