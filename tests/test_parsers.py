"""Pure-function parser tests — no network, no I/O."""
import unittest

from tcg.cards import dedupe_lines, detect_game, parse_card_line
from tcg.wishlist import is_deal, parse_wishlist_entry, should_send_alert


class TestDetectGame(unittest.TestCase):
    def test_no_prefix_returns_default(self):
        self.assertEqual(detect_game("Black Lotus #001"), ('MTG', 'Black Lotus #001'))

    def test_no_prefix_uses_explicit_default(self):
        self.assertEqual(detect_game("Dark Magician", default='YGO'), ('YGO', 'Dark Magician'))

    def test_ygo_prefix(self):
        self.assertEqual(detect_game("[YGO] Dark Magician"), ('YGO', 'Dark Magician'))

    def test_pkm_prefix(self):
        self.assertEqual(detect_game("[PKM] Pikachu #base-25"), ('PKM', 'Pikachu #base-25'))

    def test_mtg_prefix(self):
        self.assertEqual(detect_game("[MTG] Black Lotus"), ('MTG', 'Black Lotus'))

    def test_prefix_case_insensitive(self):
        self.assertEqual(detect_game("[ygo] Dark Magician"), ('YGO', 'Dark Magician'))


class TestParseCardLine(unittest.TestCase):
    def test_plain(self):
        qty, card, foil, buy = parse_card_line("Black Lotus #001")
        self.assertEqual((qty, card, foil, buy), (1, "Black Lotus #001", False, None))

    def test_quantity(self):
        qty, card, foil, buy = parse_card_line("3x Counterspell")
        self.assertEqual((qty, card, foil, buy), (3, "Counterspell", False, None))

    def test_foil(self):
        qty, card, foil, _ = parse_card_line("Lightning Bolt (Foil) #042")
        self.assertEqual((qty, foil), (1, True))
        self.assertNotIn("(Foil)", card)
        self.assertEqual(card, "Lightning Bolt #042")

    def test_buy_price(self):
        qty, card, _, buy = parse_card_line("Tarmogoyf | 25.50")
        self.assertEqual((qty, buy), (1, 25.50))
        self.assertEqual(card, "Tarmogoyf")

    def test_all_modifiers(self):
        qty, card, foil, buy = parse_card_line("2x Iroh (Foil) #349 | 12.50")
        self.assertEqual(qty, 2)
        self.assertEqual(buy, 12.50)
        self.assertTrue(foil)
        self.assertEqual(card, "Iroh #349")

    def test_surge_foil_detected(self):
        _, card, foil, _ = parse_card_line("Lightning Bolt (Surge Foil) #150")
        self.assertTrue(foil)
        self.assertNotIn("Surge Foil", card)

    def test_borderless_foil_detected(self):
        _, card, foil, _ = parse_card_line("Black Lotus (Borderless) (Foil) #039")
        self.assertTrue(foil)
        self.assertIn("(Borderless)", card)   # non-foil parenthetical preserved
        self.assertNotIn("(Foil)", card)

    def test_foil_etched_detected(self):
        _, _, foil, _ = parse_card_line("Tarmogoyf (Foil Etched) #100")
        self.assertTrue(foil)

    def test_invalid_buy_price_ignored(self):
        qty, card, _, buy = parse_card_line("Card | not_a_price")
        self.assertIsNone(buy)
        self.assertEqual(card, "Card")


class TestDedupeLines(unittest.TestCase):
    def test_preserves_order(self):
        self.assertEqual(dedupe_lines(["a\n", "b\n", "a\n", "c\n"]), ["a", "b", "c"])

    def test_drops_empty(self):
        self.assertEqual(dedupe_lines(["\n", "  \n", "x\n"]), ["x"])


class TestParseWishlistEntry(unittest.TestCase):
    def test_basic_lt(self):
        e = parse_wishlist_entry("Black Lotus | < 100.00")
        self.assertEqual(e['game'], 'MTG')
        self.assertEqual(e['operator'], '<')
        self.assertEqual(e['target_price'], 100.00)
        self.assertEqual(e['card_line'], "Black Lotus")

    def test_lte(self):
        self.assertEqual(parse_wishlist_entry("X | <= 5")['operator'], '<=')

    def test_gte(self):
        self.assertEqual(parse_wishlist_entry("X | >= 5")['operator'], '>=')

    def test_gt(self):
        self.assertEqual(parse_wishlist_entry("X | > 5")['operator'], '>')

    def test_dollar_sign_stripped(self):
        self.assertEqual(parse_wishlist_entry("X | < $5.50")['target_price'], 5.50)

    def test_ygo_prefix(self):
        self.assertEqual(parse_wishlist_entry("[YGO] Dark Magician | < 10")['game'], 'YGO')

    def test_pkm_prefix(self):
        self.assertEqual(parse_wishlist_entry("[PKM] Pikachu #base-25 | < 10")['game'], 'PKM')

    def test_comment_ignored(self):
        self.assertIsNone(parse_wishlist_entry("# this is a comment"))

    def test_empty_ignored(self):
        self.assertIsNone(parse_wishlist_entry("   "))

    def test_no_pipe_ignored(self):
        self.assertIsNone(parse_wishlist_entry("Just a card name"))

    def test_invalid_target_ignored(self):
        self.assertIsNone(parse_wishlist_entry("X | < not_a_number"))


class TestIsDeal(unittest.TestCase):
    def test_lt(self):
        self.assertTrue(is_deal(5.0, '<', 10.0))
        self.assertFalse(is_deal(10.0, '<', 10.0))

    def test_lte(self):
        self.assertTrue(is_deal(10.0, '<=', 10.0))
        self.assertFalse(is_deal(10.01, '<=', 10.0))

    def test_gt(self):
        self.assertTrue(is_deal(11.0, '>', 10.0))
        self.assertFalse(is_deal(10.0, '>', 10.0))

    def test_gte(self):
        self.assertTrue(is_deal(10.0, '>=', 10.0))
        self.assertFalse(is_deal(9.99, '>=', 10.0))


class TestShouldSendAlert(unittest.TestCase):
    def test_never_alerted(self):
        self.assertTrue(should_send_alert("X", {}))

    def test_within_cooldown(self):
        from datetime import datetime, timedelta
        recent = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        self.assertFalse(should_send_alert("X", {"X": recent}, cooldown_days=7))

    def test_after_cooldown(self):
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        self.assertTrue(should_send_alert("X", {"X": old}, cooldown_days=7))

    def test_malformed_date(self):
        self.assertTrue(should_send_alert("X", {"X": "not-a-date"}))


if __name__ == '__main__':
    unittest.main()
