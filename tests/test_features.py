import tempfile
import unittest

from tcg_tracker.analytics import data_health, portfolio_breakdowns
from tcg_tracker.importer import parse_collection_csv
from tcg_tracker.storage import TrackerStore


class CollectionManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TrackerStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_update_card_rewrites_source_and_preserves_identity_response(self):
        result = self.store.add_card("MTG", "Lightning Bolt #150", 1, "regular", "1.00", "NM")

        updated = self.store.update_card(
            result["card_id"],
            {"quantity": 3, "condition": "LP", "finish": "foil", "buy_price": "1.25"},
        )

        self.assertEqual(
            self.store.card_file("MTG").read_text(encoding="utf-8"),
            "3x Lightning Bolt #150 (Foil) [LP] | 1.25\n",
        )
        self.assertNotEqual(updated["card_id"], result["card_id"])

    def test_partial_sale_reduces_quantity_and_records_profit(self):
        result = self.store.add_card("MTG", "Lightning Bolt #150", 3, "regular", "1.00", "NM")

        sale = self.store.sell_card(result["card_id"], 1, 5.0, fees=0.5, shipping=0.25)

        self.assertEqual(sale["net_amount"], 4.25)
        self.assertEqual(sale["realized_profit"], 3.25)
        self.assertIn("2x Lightning Bolt #150", self.store.card_file("MTG").read_text())
        self.assertEqual(self.store.list_transactions()[0]["type"], "sale")

    def test_wishlist_crud_and_alert_setting(self):
        added = self.store.add_wishlist("PKM", "Pikachu # base-25", "<=", 20, False)
        item = self.store.read_wishlist(limit=0)[0]
        self.assertFalse(item["alert_enabled"])

        updated = self.store.update_wishlist(
            added["wishlist_id"], {"target_price": 18, "alert_enabled": True}
        )
        self.assertEqual(self.store.read_wishlist(limit=0)[0]["target_price"], 18)
        self.assertTrue(self.store.read_wishlist(limit=0)[0]["alert_enabled"])

        self.store.delete_wishlist(updated["wishlist_id"])
        self.assertEqual(self.store.read_wishlist(limit=0), [])

    def test_backup_round_trip_restores_private_data(self):
        self.store.add_card("YGO", "Dark Magician")
        self.store.add_wishlist("YGO", "Blue-Eyes White Dragon", "<", 10)
        backup = self.store.create_backup().getvalue()

        with tempfile.TemporaryDirectory() as restore_dir:
            restored = TrackerStore(restore_dir)
            result = restored.restore_backup(backup)

            self.assertIn("ygo_cards.txt", result["files"])
            self.assertEqual(restored.read_entries()[0].name, "Dark Magician")
            self.assertEqual(restored.read_wishlist(limit=0)[0]["card_line"], "Blue-Eyes White Dragon")


class ImportTests(unittest.TestCase):
    def test_common_csv_headings_are_normalized(self):
        rows = parse_collection_csv(
            b"Product Line,Card Name,Collector Number,Qty,Printing,Card Condition,Price Paid\n"
            b"Magic: The Gathering,Lightning Bolt,150,2,Foil,LP,1.25\n"
        )

        self.assertEqual(rows[0]["game"], "MTG")
        self.assertEqual(rows[0]["card_line"], "Lightning Bolt # 150")
        self.assertEqual(rows[0]["quantity"], 2)
        self.assertEqual(rows[0]["finish"], "foil")
        self.assertTrue(rows[0]["valid"])


class AnalyticsTests(unittest.TestCase):
    def test_foreign_currency_is_not_mixed_into_usd_total(self):
        data = portfolio_breakdowns(
            [
                {"name": "USD Card", "game": "MTG", "value": 10, "currency": "USD", "quantity": 1},
                {"name": "EUR Card", "game": "PKM", "value": 20, "currency": "EUR", "quantity": 1},
            ]
        )

        self.assertEqual(data["total_value"], 10)
        self.assertEqual(data["foreign_totals"]["EUR"], 20)

    def test_health_flags_large_history_drop(self):
        report = data_health(
            {"cards": [], "failures": []},
            [
                {"date": "2026-07-27", "value": 500.0},
                {"date": "2026-07-28", "value": 100.0},
                {"date": "2026-07-29", "value": 510.0},
            ],
        )

        self.assertTrue(any(row["date"] == "2026-07-28" for row in report["anomalies"]))


if __name__ == "__main__":
    unittest.main()
