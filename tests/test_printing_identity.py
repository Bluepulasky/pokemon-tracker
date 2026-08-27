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
                                 "condition": "M/NM", "language": "en", "quantity": 1})
    assert est["basis"] == "no_data"
    assert est["total"] is None
    assert "impresión" in est["reason"]


def test_a_price_is_never_taken_from_another_variant(repo, pricing):
    """Previously any priced variant of the card would do, so a reprint was
    valued at the original's price."""
    repo.upsert_price("base1-4", "reverse", "cardmarket", "EUR", 9.0,
                      None, None, None, None)
    est = pricing.estimate_item({"card_id": "base1-4", "variant": "first_edition",
                                 "condition": "M/NM", "language": "en", "quantity": 1})
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


# ---------------------------------------------- end to end through the service
def test_print_runs_of_one_card_price_apart(tmp_path):
    """The reported bug, end to end: one Hitmonchan owned in three printings used
    to read a single number for all three."""
    import json
    import pathlib

    from tombot.config import DEFAULT_MODIFIERS
    from tombot.services.repository import PokemonRepo
    from tombot.services.sources.tcgdex import parse_variants

    fixtures = pathlib.Path(__file__).parent / "fixtures" / "tcgdex"

    class FixtureSource:
        def fetch_prices(self, card_ids):
            return {c: {"source": "cardmarket",
                        "variants": parse_variants(
                            json.loads((fixtures / f"{c}.json").read_text()))}
                    for c in card_ids if (fixtures / f"{c}.json").exists()}

    repo = PokemonRepo(tmp_path / "e2e.db")
    repo.init_db(DEFAULT_MODIFIERS)
    repo.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                              "printed_total": 102, "total": 102,
                              "release_date": "1999/01/09", "ptcgo_code": None,
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "base1-7", "official_set_id": "base1",
                        "name": "Hitmonchan", "number": "7"}])
    for variant in ("holo", "shadowless", "first_edition"):
        repo.upsert_collection_item({"card_id": "base1-7", "variant": variant,
                                     "condition": "GD", "language": "en"})

    svc = PricingService(repo, FixtureSource(), Config)
    assert svc.refresh(all_cards=True)["updated"] == 3

    mods = repo.get_modifiers()
    got = {i["variant"]: svc.estimate_item(i, mods)
           for i in repo.items_by_card("base1-7")}

    assert got["holo"]["variant_key"] == "holo:unlimited"
    assert got["shadowless"]["variant_key"] == "holo:shadowless"
    assert got["first_edition"]["variant_key"] == "holo:shadowless:1st-edition"

    # MP is 0.70; the Shadowless product is 23.50 against Unlimited at 14.29
    assert got["holo"]["unit"] == 10.0
    assert got["shadowless"]["unit"] == 16.45
    # and the 1st edition carries the x2 premium on top
    assert got["first_edition"]["unit"] == 32.9
    assert got["first_edition"]["variant_multiplier"] == 2.0


def test_a_manual_price_wins_and_survives_a_refresh(tmp_path):
    """Promos and other gaps are corrected by hand, so a refresh must never
    overwrite what the user typed."""
    import json
    import pathlib

    from tombot.config import DEFAULT_MODIFIERS
    from tombot.services.repository import PokemonRepo
    from tombot.services.sources.tcgdex import parse_variants

    fixtures = pathlib.Path(__file__).parent / "fixtures" / "tcgdex"

    class FixtureSource:
        def fetch_prices(self, card_ids):
            return {c: {"source": "cardmarket",
                        "variants": parse_variants(
                            json.loads((fixtures / f"{c}.json").read_text()))}
                    for c in card_ids if (fixtures / f"{c}.json").exists()}

    repo = PokemonRepo(tmp_path / "manual.db")
    repo.init_db(DEFAULT_MODIFIERS)
    repo.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                              "printed_total": 102, "total": 102,
                              "release_date": "1999/01/09", "ptcgo_code": None,
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "base1-7", "official_set_id": "base1",
                        "name": "Hitmonchan", "number": "7"}])
    repo.upsert_collection_item({"card_id": "base1-7", "variant": "holo",
                                 "condition": "M/NM", "language": "en"})

    svc = PricingService(repo, FixtureSource(), Config)
    svc.refresh(all_cards=True)
    repo.set_manual_price("base1-7", "holo", 9.99)

    result = svc.refresh(all_cards=True)
    assert result["manual_kept"] == 1 and result["updated"] == 0

    item = repo.items_by_card("base1-7")[0]
    estimate = svc.estimate_item(item, repo.get_modifiers())
    assert estimate["unit"] == 9.99 and estimate["manual"] is True

    # clearing it falls back to the feed
    repo.set_manual_price("base1-7", "holo", None)
    estimate = svc.estimate_item(repo.items_by_card("base1-7")[0], repo.get_modifiers())
    assert estimate["unit"] == 14.29 and estimate["manual"] is False
