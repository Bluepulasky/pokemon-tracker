"""Refusing a price that belongs to a different card.

TCGdex reports one Cardmarket product for both prints of a WOTC rare, so the
non-holo carries the holo's price — four to six times too high. These tests run
against real payloads captured from the live API.
"""
import json
import pathlib

import pytest

from tombot.config import DEFAULT_MODIFIERS, Config
from tombot.services import trust
from tombot.services.pricing import PricingService
from tombot.services.repository import PokemonRepo
from tombot.services.sources.tcgdex import parse_variants

FIX = pathlib.Path(__file__).parent / "fixtures" / "tcgdex"


class TcgdexFixture:
    """The primary provider, replaying real captured payloads."""
    name = "tcgdex"

    def fetch_prices(self, card_ids):
        return {c: {"source": "cardmarket",
                    "variants": parse_variants(json.loads((FIX / f"{c}.json").read_text()))}
                for c in card_ids if (FIX / f"{c}.json").exists()}


class CrosscheckFixture:
    """The second provider: one product per card, plus a second market."""
    name = "pokemontcgio"

    def __init__(self, prices=None):
        self.prices = prices or {}
        self.asked = []

    def fetch_prices(self, card_ids):
        self.asked.append(sorted(card_ids))
        return {c: v for c, v in self.prices.items() if c in card_ids}


def build(tmp_path, cards, owned):
    repo = PokemonRepo(tmp_path / "c.db")
    repo.init_db(DEFAULT_MODIFIERS)
    repo.upsert_official_set({"id": "base2", "name": "Jungle", "series": "Base",
                              "printed_total": 64, "total": 64,
                              "release_date": "1999/06/16", "ptcgo_code": None,
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards(cards)
    for card_id, variant in owned:
        repo.upsert_collection_item({"card_id": card_id, "variant": variant,
                                     "condition": "M/NM", "language": "en"})
    return repo


JUNGLE_FLAREON = [
    {"id": "base2-3", "official_set_id": "base2", "name": "Flareon", "number": "3"},
    {"id": "base2-19", "official_set_id": "base2", "name": "Flareon", "number": "19"},
]


def test_the_collision_this_guards_against_is_real():
    """The captured payloads must still show both Flareons on one product.

    If TCGdex fixes their data this fails, which is the point: the guard should
    be removed deliberately, not left rotting in place.
    """
    a = json.loads((FIX / "base2-3.json").read_text())
    b = json.loads((FIX / "base2-19.json").read_text())
    pid_a = (a["pricing"]["cardmarket"])["idProduct"]
    pid_b = (b["pricing"]["cardmarket"])["idProduct"]
    assert pid_a == pid_b == 273800
    assert trust.product_is_shared(273800)
    assert sorted(trust.cards_sharing(273800)) == ["base2-19", "base2-3"]


def test_a_shared_product_is_refused_and_the_second_provider_prices_it(tmp_path):
    """The non-holo must not inherit the holo's 46.57."""
    repo = build(tmp_path, JUNGLE_FLAREON, [("base2-19", "normal")])
    alt = CrosscheckFixture({"base2-19": {
        "source": "cardmarket", "currency": "EUR",
        "prices": {"averageSellPrice": 10.39, "trendPrice": 8.85, "lowPrice": 1.0},
    }})
    svc = PricingService(repo, TcgdexFixture(), Config, crosscheck=alt)

    result = svc.refresh(all_cards=True)

    assert result["refused"] == 1
    assert result["recovered"] == 1
    price = repo.get_price("base2-19", "normal")
    assert price["price"] == pytest.approx(10.39)      # not 46.57


def test_the_refused_quote_is_kept_and_says_who_else_claims_it(tmp_path):
    """A refused price stays visible with its reason; silence teaches nothing."""
    repo = build(tmp_path, JUNGLE_FLAREON, [("base2-19", "normal")])
    alt = CrosscheckFixture({"base2-19": {
        "source": "cardmarket", "currency": "EUR",
        "prices": {"averageSellPrice": 10.39},
    }})
    PricingService(repo, TcgdexFixture(), Config, crosscheck=alt).refresh(all_cards=True)

    quotes = repo.quotes_for_card("base2-19")
    refused = [q for q in quotes if not q["trusted"]]
    assert len(refused) == 1
    assert refused[0]["provider"] == "tcgdex"
    assert refused[0]["price"] == pytest.approx(46.57)
    assert "base2-3" in refused[0]["distrust_reason"]

    trusted = [q for q in quotes if q["trusted"]]
    assert [q["provider"] for q in trusted] == ["pokemontcgio"]


def test_a_clean_product_still_uses_the_primary_provider(tmp_path):
    """Base Set has no collisions and keeps its per-print-run granularity."""
    repo = PokemonRepo(tmp_path / "clean.db")
    repo.init_db(DEFAULT_MODIFIERS)
    repo.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                              "printed_total": 102, "total": 102,
                              "release_date": "1999/01/09", "ptcgo_code": None,
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "base1-7", "official_set_id": "base1",
                        "name": "Hitmonchan", "number": "7"}])
    repo.upsert_collection_item({"card_id": "base1-7", "variant": "holo",
                                 "condition": "M/NM", "language": "en"})
    alt = CrosscheckFixture()
    svc = PricingService(repo, TcgdexFixture(), Config, crosscheck=alt)

    result = svc.refresh(all_cards=True)

    assert result["refused"] == 0
    assert result["updated"] == 1
    row = repo.get_price("base1-7", "holo")
    assert row["variant_key"]                       # the print run was recorded
    assert row["market_product_id"]


def test_tcgplayer_quotes_are_recorded_but_never_priced_in(tmp_path):
    """A different market in a different currency is reference, not valuation."""
    repo = build(tmp_path, JUNGLE_FLAREON, [("base2-19", "normal")])
    alt = CrosscheckFixture({"base2-19": {
        "source": "cardmarket", "currency": "EUR",
        "prices": {"averageSellPrice": 10.39},
        "tcgplayer": {"currency": "USD", "printings": {
            "unlimited": {"low": 9.0, "mid": 12.43, "high": 999.0, "market": 15.41},
        }},
    }})
    PricingService(repo, TcgdexFixture(), Config, crosscheck=alt).refresh(all_cards=True)

    usd = [q for q in repo.quotes_for_card("base2-19") if q["market"] == "tcgplayer"]
    assert len(usd) == 1
    assert usd[0]["currency"] == "USD"
    assert usd[0]["price"] == pytest.approx(15.41)
    assert usd[0]["price_low"] == pytest.approx(9.0)

    # The valuation stays in EUR from Cardmarket.
    price = repo.get_price("base2-19", "normal")
    assert price["currency"] == "EUR"
    assert price["price"] == pytest.approx(10.39)


def test_a_refused_card_with_no_second_opinion_stays_unpriced(tmp_path):
    """Better no number than a number belonging to another card."""
    repo = build(tmp_path, JUNGLE_FLAREON, [("base2-19", "normal")])
    svc = PricingService(repo, TcgdexFixture(), Config,
                         crosscheck=CrosscheckFixture())

    result = svc.refresh(all_cards=True)

    assert result["refused"] == 1
    assert result["unpriced"] == 1
    assert repo.get_price("base2-19", "normal") is None


# ------------------------------------------- pricing from the chosen product

class ProductFixture:
    """A source that only answers product lookups, like tcggo does."""
    name = "tcggo"

    def __init__(self, by_id):
        self.by_id = by_id
        self.asked = []

    def fetch_by_products(self, ids):
        self.asked.append(sorted(ids))
        return {i: self.by_id[i] for i in ids if i in self.by_id}

    def fetch_prices(self, card_ids):
        raise AssertionError("must not resolve when the product is known")


def test_a_row_that_names_its_product_is_priced_by_lookup(tmp_path):
    """No variant translated, no printing resolved — the two steps that broke."""
    repo = build(tmp_path, JUNGLE_FLAREON, [])
    repo.upsert_collection_item({"card_id": "base2-19", "variant": "normal",
                                 "condition": "M/NM", "language": "en",
                                 "market_product_id": 273816})

    source = ProductFixture({273816: {
        "currency": "EUR", "price": 12.24, "lowest_near_mint": 1.49,
        "version": "Unlimited",
    }})
    svc = PricingService(repo, source, Config, crosscheck=CrosscheckFixture())

    result = svc.refresh(all_cards=True)

    assert result["by_product"] == 1
    assert source.asked == [[273816]]
    row = repo.get_price("base2-19", "normal")
    assert row["price"] == pytest.approx(12.24)
    assert row["market_product_id"] == 273816


def test_products_are_looked_up_in_one_batch(tmp_path):
    """Twenty per request is the difference between 10 requests and 200."""
    cards = JUNGLE_FLAREON + [
        {"id": "base2-1", "official_set_id": "base2", "name": "Clefable", "number": "1"},
    ]
    repo = build(tmp_path, cards, [])
    for card_id, pid in (("base2-19", 273816), ("base2-3", 273800), ("base2-1", 273798)):
        repo.upsert_collection_item({"card_id": card_id, "variant": "normal",
                                     "condition": "M/NM", "language": "en",
                                     "market_product_id": pid})

    source = ProductFixture({pid: {"currency": "EUR", "price": 10.0,
                                   "lowest_near_mint": 9.0, "version": "Unlimited"}
                             for pid in (273816, 273800, 273798)})
    PricingService(repo, source, Config,
                   crosscheck=CrosscheckFixture()).refresh(all_cards=True)

    assert len(source.asked) == 1, "one call, not one per card"
    assert source.asked[0] == [273798, 273800, 273816]


def test_rows_without_a_product_still_use_the_old_path(tmp_path):
    """Cards registered before the picker existed must keep being priced."""
    repo = build(tmp_path, JUNGLE_FLAREON, [("base2-19", "normal")])
    alt = CrosscheckFixture({"base2-19": {
        "source": "cardmarket", "currency": "EUR",
        "prices": {"averageSellPrice": 10.39},
    }})
    svc = PricingService(repo, TcgdexFixture(), Config, crosscheck=alt)

    result = svc.refresh(all_cards=True)

    assert result["by_product"] == 0
    assert repo.get_price("base2-19", "normal")["price"] == pytest.approx(10.39)
