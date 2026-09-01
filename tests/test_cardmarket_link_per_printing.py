"""The Cardmarket link must follow the chosen printing, not the card (issue #27).

A Flareon added as Normal (Cardmarket V2) was linking to the Holo (V1) listing,
because the link came from the card, which resolves to one product for the
whole card. A row that chose a version knows its exact product, so it uses that
product's own URL.
"""
import pytest

from tombot.config import Config
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "c.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)

    repo = PokemonRepo(Config.DB_PATH)
    repo.init_db()
    repo.upsert_official_set({"id": "ju", "name": "Jungle", "series": "Base",
                              "printed_total": 64, "total": 64,
                              "release_date": "1999/06/16", "ptcgo_code": "JU",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "ju-19", "official_set_id": "ju", "name": "Flareon",
                        "number": "19", "rarity": "Rare"}])
    # Two real Cardmarket products for Flareon: the holo (V1) and the non-holo (V2).
    repo.upsert_market_products([
        {"product_id": 273800, "episode_id": 170, "card_id": "ju-3", "code": "JU 3",
         "number": "3", "name": "Flareon", "version": "Unlimited", "rarity": "Holo",
         "currency": "EUR", "price": 49.0, "price_low": None, "price_avg30": None,
         "price_avg7": None, "available": 1,
         "image": None, "market_url": "https://cardmarket.com/…/Flareon-V1-JU3"},
        {"product_id": 273816, "episode_id": 170, "card_id": "ju-19", "code": "JU 19",
         "number": "19", "name": "Flareon", "version": "Unlimited", "rarity": "rare",
         "currency": "EUR", "price": 12.0, "price_low": None, "price_avg30": None,
         "price_avg7": None, "available": 1,
         "image": None, "market_url": "https://cardmarket.com/…/Flareon-V2-JU19"},
    ])
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    return a


def test_the_row_links_to_its_chosen_product(app):
    """A Normal Flareon pinned to product 273816 must link to V2, not V1."""
    repo = app.extensions["repo"]
    repo.upsert_collection_item({"card_id": "ju-19", "variant": "normal",
                                 "condition": "M/NM", "language": "es",
                                 "market_product_id": 273816})

    rows = app.test_client().get("/api/collection/by-card/ju-19").get_json()["data"]

    assert len(rows) == 1
    assert rows[0]["market_url"].endswith("Flareon-V2-JU19")


def test_a_row_without_a_chosen_product_uses_the_cards_direct_match(app):
    """A row that never pinned a version links to the card's own Cardmarket
    product (the direct tcggo<->MKM match by card_id), not the dead
    prices.pokemontcg.io redirector (issue #27, reopened)."""
    repo = app.extensions["repo"]
    repo.upsert_collection_item({"card_id": "ju-19", "variant": "normal",
                                 "condition": "M/NM", "language": "es"})

    rows = app.test_client().get("/api/collection/by-card/ju-19").get_json()["data"]

    url = rows[0]["market_url"]
    assert url is not None
    assert "pokemontcg.io" not in url, "the dead redirector must be gone"
    # ju-19's only product is V2; the direct match resolves to it (V1 is ju-3).
    assert url.endswith("Flareon-V2-JU19")
