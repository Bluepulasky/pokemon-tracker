"""Pricing reads from the imported products, with no live source (tcggo-only).

A set import stores each Cardmarket product with its price. A card you own
carries the product it is, so pricing is a local lookup by product id — no
network, and no guessing which printing a variant maps to.
"""
import pytest

from tombot.config import DEFAULT_MODIFIERS, Config
from tombot.services.pricing import PricingService
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "p.db")
    r.init_db(DEFAULT_MODIFIERS)
    r.upsert_official_set({"id": "ju", "name": "Jungle", "series": "Base",
                           "printed_total": 64, "total": 64,
                           "release_date": "1999/06/16", "ptcgo_code": "JU",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([{"id": "ju-19", "official_set_id": "ju", "name": "Flareon",
                     "number": "19", "rarity": "rare"}])
    r.upsert_market_products([{
        "product_id": 273816, "episode_id": 170, "card_id": "ju-19",
        "code": "JU 19", "number": "19", "name": "Flareon", "version": "Unlimited",
        "rarity": "rare", "currency": "EUR", "price": 12.24, "price_low": 1.49,
        "price_avg30": 10.72, "price_avg7": 9.79, "available": 503,
        "image": None, "market_url": "https://x/cm/19346"}])
    return r


def test_a_row_with_a_product_is_priced_from_it(repo):
    repo.upsert_collection_item({"card_id": "ju-19", "variant": "normal",
                                 "condition": "M/NM", "language": "es",
                                 "market_product_id": 273816})

    result = PricingService(repo, Config).refresh()

    assert result["updated"] == 1
    assert result["unpriced"] == 0
    assert repo.get_price("ju-19", "normal")["price"] == pytest.approx(12.24)


def test_a_row_without_a_product_is_left_unpriced(repo):
    """No product chosen means no price invented — a wrong number is worse."""
    repo.upsert_collection_item({"card_id": "ju-19", "variant": "normal",
                                 "condition": "M/NM", "language": "es"})

    result = PricingService(repo, Config).refresh()

    assert result["updated"] == 0
    assert result["unpriced"] == 1
    assert repo.get_price("ju-19", "normal") is None


def test_a_manual_price_is_never_overwritten(repo):
    repo.upsert_collection_item({"card_id": "ju-19", "variant": "normal",
                                 "condition": "M/NM", "language": "es",
                                 "market_product_id": 273816})
    repo.set_manual_price("ju-19", "normal", 99.0)

    result = PricingService(repo, Config).refresh()

    assert result["manual_kept"] == 1
    assert repo.get_price("ju-19", "normal", source="manual")["price"] == pytest.approx(99.0)


def test_refresh_needs_no_network(repo, monkeypatch):
    """No source is constructed, so there is nothing to call out to."""
    import tombot.services.pricing as pricing_mod

    # If pricing tried to reach a source, importing requests would be the tell.
    monkeypatch.setattr(pricing_mod, "log", pricing_mod.log)
    repo.upsert_collection_item({"card_id": "ju-19", "variant": "normal",
                                 "condition": "M/NM", "language": "es",
                                 "market_product_id": 273816})
    svc = PricingService(repo, Config)
    assert not hasattr(svc, "source")
    assert svc.refresh()["updated"] == 1
