"""The version picker is the single selector for adding a card.

The Edición/Variante dropdowns are gone: a chosen Cardmarket product decides
which card the row is and which variant it represents. The backend derives the
variant from the product, which is also what keeps two products of the same card
(e.g. Unlimited vs 1st Edition Shadowless) in distinct collection rows.
"""
import pytest

from tombot.config import Config
from tombot.services.printing_variants import variant_from_product
from tombot.services.repository import PokemonRepo


@pytest.mark.parametrize("version,rarity,expected", [
    ("Unlimited", "Common", "normal"),
    ("Unlimited", "Rare Holo", "holo"),
    ("1st Edition", "Rare", "first_edition"),
    ("Shadowless", "Rare Holo", "shadowless"),
    # "1st Edition Shadowless" is a shadowless run — shadowless wins over 1st ed.
    ("1st Edition Shadowless", "Rare Holo", "shadowless"),
    ("Reverse Holo", "Rare", "reverse"),
    (None, None, "normal"),
])
def test_variant_from_product(version, rarity, expected):
    assert variant_from_product(version, rarity) == expected


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
    repo.upsert_official_set({"id": "bs", "name": "Base Set", "series": "Base",
                              "printed_total": 102, "total": 102,
                              "release_date": "1999/01/09", "ptcgo_code": "BS",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "bs-3", "official_set_id": "bs", "name": "Chansey",
                        "number": "3", "rarity": "Rare Holo"}])
    # Two real products of the SAME card: Unlimited and 1st Edition Shadowless.
    repo.upsert_market_products([
        {"product_id": 273698, "episode_id": 1, "card_id": "bs-3", "code": "BS 3",
         "number": "3", "name": "Chansey", "version": "Unlimited",
         "rarity": "Rare Holo", "currency": "EUR", "price": 5.0, "price_low": None,
         "price_avg30": None, "price_avg7": None, "available": 1, "image": None,
         "market_url": "https://cardmarket.com/…/Chansey-BS3"},
        {"product_id": 19394, "episode_id": 1, "card_id": "bs-3", "code": "BS 3",
         "number": "3", "name": "Chansey", "version": "1st Edition Shadowless",
         "rarity": "Rare Holo", "currency": "EUR", "price": 22.0, "price_low": None,
         "price_avg30": None, "price_avg7": None, "available": 1, "image": None,
         "market_url": "https://cardmarket.com/…/Chansey-V2-BS3"},
    ])
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    return a


def test_add_derives_variant_from_the_chosen_product(app):
    """The client sends only the product; the row's variant comes from it."""
    client = app.test_client()
    r = client.post("/api/collection", json={
        "card_id": "bs-3", "market_product_id": 19394,
        "condition": "M/NM", "language": "es", "quantity": 1})
    assert r.status_code == 201
    assert r.get_json()["variant"] == "shadowless"


def test_two_products_of_one_card_are_distinct_rows(app):
    """Holding both the Unlimited and the 1st Ed Shadowless Chansey must not
    collapse into a single row — the derived variant keeps them apart."""
    client = app.test_client()
    client.post("/api/collection", json={
        "card_id": "bs-3", "market_product_id": 273698, "quantity": 1})
    client.post("/api/collection", json={
        "card_id": "bs-3", "market_product_id": 19394, "quantity": 1})

    rows = client.get("/api/collection/by-card/bs-3").get_json()["data"]
    variants = sorted(r["variant"] for r in rows)
    # Chansey is Rare Holo, so the Unlimited product derives "holo"; the
    # shadowless run derives "shadowless". Two products, two distinct rows.
    assert variants == ["holo", "shadowless"]
    assert all(r["quantity"] == 1 for r in rows)


def test_unknown_product_is_rejected(app):
    """A market_product_id that does not exist fails loudly, not silently."""
    r = app.test_client().post("/api/collection", json={
        "card_id": "bs-3", "market_product_id": 999999, "quantity": 1})
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "invalid_product"
