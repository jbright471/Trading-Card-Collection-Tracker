import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from tcg_tracker.core import (
    build_card_line,
    get_refresh_status,
    parse_collection_line,
    safe_html,
    update_history,
)
from tcg_tracker.pricing import (
    fetch_entry,
    pokemon_price,
    refresh_collection,
    refresh_wishlist,
    request_json,
    scryfall_to_card,
    target_is_met,
)
from tcg_tracker.storage import TrackerStore


class CardLineTests(unittest.TestCase):
    def test_parse_collection_line_reads_quantity_finish_and_buy_price(self):
        entry = parse_collection_line("3x Lightning Bolt #150 (Foil) [LP] | 1.50", "MTG")

        self.assertEqual(entry.game, "MTG")
        self.assertEqual(entry.name, "Lightning Bolt #150")
        self.assertEqual(entry.quantity, 3)
        self.assertEqual(entry.finish, "foil")
        self.assertEqual(entry.condition, "LP")
        self.assertEqual(entry.buy_price, 1.50)

    def test_build_card_line_keeps_quantity_finish_and_buy_price(self):
        line = build_card_line(
            "Lightning Bolt #150",
            quantity=3,
            finish="foil",
            buy_price="1.50",
        )

        self.assertEqual(line, "3x Lightning Bolt #150 (Foil) | 1.50")

    def test_build_card_line_omits_empty_optional_fields(self):
        line = build_card_line(
            "Dark Magician",
            quantity=1,
            finish="regular",
            buy_price="",
        )

        self.assertEqual(line, "Dark Magician")

    def test_build_card_line_keeps_non_default_condition(self):
        line = build_card_line(
            "Dark Magician",
            quantity=1,
            finish="regular",
            buy_price="",
            condition="LP",
        )

        self.assertEqual(line, "Dark Magician [LP]")

    def test_parse_collection_line_detects_variant_foil_labels(self):
        entry = parse_collection_line("Lightning Bolt (Borderless Foil) #150", "MTG")

        self.assertEqual(entry.name, "Lightning Bolt #150")
        self.assertEqual(entry.finish, "foil")


class HistoryGuardrailTests(unittest.TestCase):
    def test_update_history_skips_refresh_when_too_many_cards_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "price_history.csv"
            path.write_text("2026-06-22,100.00\n", encoding="utf-8")

            result = update_history(
                path,
                total_value=20,
                today=date(2026, 6, 23),
                failed_cards=4,
                total_cards=5,
            )

            self.assertFalse(result.updated)
            self.assertIn("failure rate", result.reason)
            self.assertEqual(path.read_text(encoding="utf-8"), "2026-06-22,100.00\n")

    def test_update_history_replaces_same_day_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "price_history.csv"
            path.write_text("2026-06-23,100.00\n", encoding="utf-8")

            result = update_history(
                path,
                total_value=125.25,
                today=date(2026, 6, 23),
                failed_cards=0,
                total_cards=5,
            )

            self.assertTrue(result.updated)
            self.assertEqual(path.read_text(encoding="utf-8"), "2026-06-23,125.25\n")


class StatusTests(unittest.TestCase):
    def test_refresh_status_marks_stale_data(self):
        status = get_refresh_status(
            last_updated="2026-05-14",
            today=date(2026, 6, 23),
            stale_after_days=2,
        )

        self.assertEqual(status["state"], "stale")
        self.assertEqual(status["days_old"], 40)


class HtmlSafetyTests(unittest.TestCase):
    def test_safe_html_escapes_user_and_api_text(self):
        self.assertEqual(
            safe_html('<script>alert("x")</script>'),
            "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;",
        )


class PricingHelperTests(unittest.TestCase):
    def test_target_operators(self):
        self.assertTrue(target_is_met(5.0, "<", 10.0))
        self.assertTrue(target_is_met(10.0, "<=", 10.0))
        self.assertTrue(target_is_met(11.0, ">", 10.0))
        self.assertTrue(target_is_met(10.0, ">=", 10.0))
        self.assertFalse(target_is_met(None, "<", 10.0))

    def test_pokemon_price_prefers_tcgplayer_market(self):
        card = {
            "pricing": {
                "tcgplayer": {
                    "holofoil": {"marketPrice": 12.34},
                }
            }
        }

        self.assertEqual(pokemon_price(card), 12.34)

    def test_refresh_wishlist_writes_price_and_image_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TrackerStore(tmp)
            store.wishlist_path.write_text(
                "Lightning Bolt #150 | < 2.00\n",
                encoding="utf-8",
            )
            card = {
                "name": "Lightning Bolt",
                "set": "Core Set",
                "price": "1.50",
                "image": "https://example.test/lightning-bolt.jpg",
                "uri": "https://example.test/lightning-bolt",
            }

            with (
                patch("tcg_tracker.pricing.fetch_entry", return_value=card),
                patch("tcg_tracker.pricing.REQUEST_DELAY_SECONDS", 0),
            ):
                result = refresh_wishlist(store, today=date(2026, 7, 26))

            cache = json.loads(store.wishlist_cache_path.read_text(encoding="utf-8"))
            self.assertEqual(result["failures"], [])
            self.assertEqual(cache["last_updated"], "2026-07-26")
            self.assertEqual(cache["items"][0]["current_price"], 1.5)
            self.assertTrue(cache["items"][0]["is_deal"])
            self.assertEqual(cache["items"][0]["image"], card["image"])

    def test_scryfall_etched_finish_uses_etched_price(self):
        card = scryfall_to_card(
            {
                "name": "Test Card",
                "prices": {"usd": "2.00", "usd_foil": "4.00", "usd_etched": "6.00"},
            },
            finish="etched",
        )

        self.assertEqual(card["price"], "6.00")
        self.assertEqual(card["price_finish"], "etched")

    def test_fetch_entry_applies_condition_multiplier(self):
        entry = parse_collection_line("Test Card [LP]", "MTG")
        provider_card = {
            "game": "MTG",
            "name": "Test Card",
            "set": "Test Set",
            "price": "10.00",
            "currency": "USD",
            "source": "Test",
        }

        with patch("tcg_tracker.pricing.fetch_mtg", return_value=provider_card):
            card = fetch_entry(entry, today=date(2026, 7, 29))

        self.assertEqual(card["unit_value"], 8.5)
        self.assertEqual(card["condition_multiplier"], 0.85)

    def test_refresh_collection_retains_last_known_value_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TrackerStore(tmp)
            store.card_file("MTG").write_text("Test Card\n", encoding="utf-8")
            card = store.load_state()["cards"][0]
            card.update({"price": 10.0, "unit_value": 10.0, "value": 10.0, "stale": False})
            store.save_state({"last_updated": "2026-07-28", "cards": [card], "failures": []})

            with (
                patch("tcg_tracker.pricing.fetch_entry", side_effect=RuntimeError("provider down")),
                patch("tcg_tracker.pricing.REQUEST_DELAY_SECONDS", 0),
            ):
                state = refresh_collection(store, today=date(2026, 7, 29))

            self.assertEqual(state["total_value"], 10.0)
            self.assertTrue(state["cards"][0]["stale"])
            self.assertFalse(state["history_updated"])

    def test_request_json_sends_json_accept_header(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true}'
        response.__exit__.return_value = False
        with patch("tcg_tracker.pricing.urllib.request.urlopen", return_value=response) as opener:
            payload = request_json("https://example.test/cards")

        request = opener.call_args.args[0]
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
