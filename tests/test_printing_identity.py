"""Printing identity: variants per edition, and honest pricing.

pokemontcg.io publishes one price per card id. Editions that are separate cards
(Base Set vs Celebrations) are therefore priced apart; variants within one
printing (Shadowless vs Unlimited) are not, because they share a card id. The
only within-printing variant the upstream ever prices separately is reverse holo.
"""
import os
import tempfile

import pytest

from tombot.config import DEFAULT_MODIFIERS, Config
from tombot.services.pricing import PricingService
from tombot.services.printing_variants import variants_for
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = PokemonRepo(path)
    r.init_db(DEFAULT_MODIFIERS)
    r.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                           "printed_total": 1, "total": 1,
                           "release_date": "1999/01/09", "ptcgo_code": None,
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([{"id": "base1-4", "official_set_id": "base1",
                     "name": "Charizard", "number": "4", "rarity": "Rare Holo"}])
    yield r
    os.unlink(path)


@pytest.fixture()
def pricing(repo):
    return PricingService(repo, None, Config)


# ---------------------------------------------------------------- variants
def test_wotc_holo_offers_the_print_run_variants():
    assert variants_for("base1", "Rare Holo") == [
        "holo", "first_edition", "shadowless", "other"]


def test_shadowless_is_base_set_only():
    """Only Base Set had a Shadowless print run; offering it elsewhere would
    invite recording a card that does not exist."""
    assert "shadowless" not in variants_for("gym1", "Rare Holo")


def test_modern_sets_offer_reverse_not_first_edition():
    v = variants_for("ex7", "Common")
    assert "reverse" in v and "first_edition" not in v


def test_holo_rares_have_no_reverse():
    assert "reverse" not in variants_for("ex7", "Rare Holo")


# ----------------------------------------------------------------- pricing
def test_reverse_holo_never_borrows_the_card_price(pricing):
    """The reported valuation bug: a reverse holo with no reverse price took the
    price of the ordinary card, which is a different object entirely."""
    prices = {"averageSellPrice": 1531.0, "trendPrice": 4184.6,
              "reverseHoloSell": 0.0, "reverseHoloTrend": 0.0}
    assert pricing._pick(prices, "reverse") is None
    assert pricing._pick(prices, "normal") == 1531.0


def test_reverse_holo_uses_its_own_price_when_present(pricing):
    prices = {"averageSellPrice": 1531.0, "reverseHoloSell": 12.5}
    assert pricing._pick(prices, "reverse") == 12.5


def test_variants_sharing_a_card_id_share_the_price(pricing):
    """Holo and non-holo of one printing are one card id upstream, so the
    card-level price is theirs, not a guess."""
    prices = {"averageSellPrice": 1531.0}
    assert pricing._pick(prices, "holo") == 1531.0
    assert pricing._pick(prices, "shadowless") == 1531.0


def test_missing_price_reports_itself(repo, pricing):
    est = pricing.estimate_item({"card_id": "base1-4", "variant": "reverse",
                                 "condition": "NM", "language": "en", "quantity": 1})
    assert est["basis"] == "no_data"
    assert est["total"] is None
    assert "impresión" in est["reason"]


def test_a_price_is_never_taken_from_another_variant(repo, pricing):
    """Previously any priced variant of the card would do, so a reprint was
    valued at the original's price."""
    repo.upsert_price("base1-4", "reverse", "cardmarket", "EUR", 9.0,
                      None, None, None, None)
    est = pricing.estimate_item({"card_id": "base1-4", "variant": "first_edition",
                                 "condition": "NM", "language": "en", "quantity": 1})
    assert est["basis"] == "no_data", "a reverse price must not value a 1st Edition"


def test_coverage_is_reported(repo, pricing):
    """A low total should read as missing data, not a cheap collection."""
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo"})
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "reverse"})
    repo.upsert_price("base1-4", "holo", "cardmarket", "EUR", 100.0,
                      None, None, None, None)
    v = pricing.value_collection()
    assert v["priced_items"] == 1 and v["unpriced_items"] == 1
    assert v["coverage_pct"] == 50.0
