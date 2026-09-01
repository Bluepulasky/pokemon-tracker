"""The version picker lists reprints of the same card across imported sets.

A Pikachu is a Pikachu whether it is Base Set, Jungle or Neo Genesis. Someone
holding one opens whatever set window and wants to find their exact printing,
so the picker shows every product of that name from every set already imported —
at no request cost, because the reprint is already in the database. Each row
carries its own card_id, so picking a reprint records the printing it actually
is, in its own set, not the card the modal was opened on.
"""
import pytest

from tombot.config import Config
from tombot.services.repository import PokemonRepo


def _pikachu_product(pid, episode, card_id, code, number, set_price, version=""):
    return {"product_id": pid, "episode_id": episode, "card_id": card_id,
            "code": code, "number": number, "name": "Pikachu", "version": version,
            "rarity": "Common", "currency": "EUR", "price": set_price,
            "price_low": None, "price_avg30": None, "price_avg7": None,
            "available": 1, "image": None,
            "market_url": f"https://cardmarket.com/…/{code}"}


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "r.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    for sid, name, code, ep, rel in (("bs", "Base Set", "BS", 1, "1999/01/09"),
                                     ("ju", "Jungle", "JU", 170, "1999/06/16"),
                                     ("ng", "Neo Genesis", "NG", 200, "2000/12/16")):
        r.upsert_official_set({"id": sid, "name": name, "series": "x",
                               "printed_total": 1, "total": 1, "release_date": rel,
                               "ptcgo_code": code, "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "bs-58", "official_set_id": "bs", "name": "Pikachu", "number": "58",
         "rarity": "Common"},
        {"id": "ju-60", "official_set_id": "ju", "name": "Pikachu", "number": "60",
         "rarity": "Common"},
        {"id": "ng-70", "official_set_id": "ng", "name": "Pikachu", "number": "70",
         "rarity": "Common"},
    ])
    r.upsert_market_products([
        _pikachu_product(1001, 1, "bs-58", "BS 58", "58", 6.73, "Unlimited"),
        _pikachu_product(1002, 1, "bs-58", "BS 58", "58", 11.40, "Oversized"),
        _pikachu_product(2001, 170, "ju-60", "JU 60", "60", 6.95, "1st Edition"),
        _pikachu_product(3001, 200, "ng-70", "NG 70", "70", 4.46, "1st Edition"),
    ])
    r.set_set_episode("bs", 1, "Base Set", "BS")
    r.set_set_episode("ju", 170, "Jungle", "JU")
    r.set_set_episode("ng", 200, "Neo Genesis", "NG")
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    return a


def _versions(app, card_id):
    return app.test_client().get(f"/api/prices/versions?card_id={card_id}").get_json()


# ------------------------------------------------------------ the repo query
def test_products_for_name_spans_every_imported_set(app):
    rows = app.extensions["repo"].market_products_for_name("Pikachu")
    assert {r["set_id"] for r in rows} == {"bs", "ju", "ng"}
    assert len(rows) == 4  # bs has two products, ju and ng one each


# --------------------------------------------------------------- the picker
def test_opening_base_set_lists_the_reprints_too(app):
    body = _versions(app, "bs-58")
    assert body["source"] == "local"
    sets = {v["set_id"] for v in body["versions"]}
    assert sets == {"bs", "ju", "ng"}          # not just Base Set


def test_the_cards_own_set_comes_first(app):
    versions = _versions(app, "bs-58")["versions"]
    # Both Base Set products lead; then the reprints follow.
    assert versions[0]["set_id"] == "bs" and versions[1]["set_id"] == "bs"
    assert versions[0]["is_current"] and versions[1]["is_current"]
    assert not versions[2]["is_current"]


def test_each_row_carries_its_own_card_and_price(app):
    by_set = {v["set_id"]: v for v in _versions(app, "bs-58")["versions"]}
    assert by_set["ju"]["card_id"] == "ju-60" and by_set["ju"]["price"] == 6.95
    assert by_set["ng"]["card_id"] == "ng-70" and by_set["ng"]["price"] == 4.46


def test_a_reprint_records_against_its_own_card(app):
    """Picking the Jungle Pikachu from Base Set's modal owns a Jungle Pikachu."""
    repo = app.extensions["repo"]
    ju = {v["set_id"]: v for v in _versions(app, "bs-58")["versions"]}["ju"]
    repo.upsert_collection_item({"card_id": ju["card_id"], "variant": "normal",
                                 "market_product_id": ju["market_product_id"]})
    owned = repo._all("SELECT card_id FROM collection_items")
    assert [o["card_id"] for o in owned] == ["ju-60"]  # Jungle, not Base Set


def test_a_card_with_no_reprints_lists_only_itself(app):
    """Neo Genesis Pikachu opened directly still shows all three — same name."""
    # (name match is the whole point; verify a name with a single set stays single)
    app.extensions["repo"].upsert_cards([
        {"id": "ju-1", "official_set_id": "ju", "name": "Clefable", "number": "1",
         "rarity": "Rare Holo"}])
    app.extensions["repo"].upsert_market_products([
        _pikachu_product(9001, 170, "ju-1", "JU 1", "1", 5.0, "1st Edition")])
    # rename that product's name to Clefable so it is a distinct card
    app.extensions["repo"]._all(
        "UPDATE market_products SET name='Clefable' WHERE product_id=9001")
    body = _versions(app, "ju-1")
    assert {v["set_id"] for v in body["versions"]} == {"ju"}
