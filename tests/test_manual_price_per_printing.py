"""A manual price belongs to the printing being edited (#88).

Tom opened his Base Set Blastoise, whose tile also stands for the Celebrations
reprint he owns, typed €10 on the Celebrations copy, and the price landed on the
Base Set card instead. The copy he was editing stayed unpriced and the one he
was not looking at became €10.

The endpoint was always addressed correctly; the modal sent it the card it had
open rather than the card of the copy. These tests pin the behaviour the modal
depends on, and the `base` field it needs to hand a typed price back unchanged.
"""
import json

import pytest

from tombot.config import Config
from tombot.services.pricing import PricingService
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "mp.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    for sid, name, rel, code in (("bs", "Base", "1999/01/09", "BS"),
                                 ("cel", "Celebrations", "2021/10/08", "CEL")):
        r.upsert_official_set({"id": sid, "name": name, "series": "Base",
                               "printed_total": 2, "total": 2, "release_date": rel,
                               "ptcgo_code": code, "logo_url": None, "symbol_url": None})
    # One Blastoise, two printings — the shape a Cartas tile collapses (#78).
    r.upsert_cards([
        {"id": "bs-2", "official_set_id": "bs", "name": "Blastoise", "number": "2",
         "rarity": "Rare Holo", "artist": "Ken Sugimori"},
        {"id": "cel-2", "official_set_id": "cel", "name": "Blastoise", "number": "2",
         "rarity": "Classic Collection", "artist": "Ken Sugimori"},
    ])
    r.upsert_collection_set({"id": "bs-completo", "name": "Base",
                             "rules_json": json.dumps({"include_sets": ["bs"]})})
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.extensions["setbuilder"].build("bs-completo")
    # He owns the Celebrations copy.
    a.extensions["repo"].upsert_collection_item(
        {"card_id": "cel-2", "variant": "normal", "condition": "M/NM", "language": "es"})
    return a


def _value(app, card_id, **over):
    item = {"card_id": card_id, "variant": "normal", "condition": "M/NM",
            "language": "en", "quantity": 1, **over}
    return PricingService(app.extensions["repo"], Config).estimate_item(item)


def test_the_value_carries_the_price_before_multipliers(app):
    """`unit` is discounted, `base` is what was typed. The form needs `base`."""
    app.extensions["repo"].set_manual_price("cel-2", "normal", 15.0)
    v = _value(app, "cel-2", condition="GD")
    assert v["base"] == 15.0          # what the user typed
    assert v["unit"] == 10.5          # 15 × 0.70, what the copy is worth
    assert v["manual"] is True


def test_two_grades_of_one_printing_share_the_typed_price(app):
    """The price is the printing's, so both copies offer 15 back, not 12.75/10.5."""
    app.extensions["repo"].set_manual_price("cel-2", "normal", 15.0)
    assert _value(app, "cel-2", condition="EX")["base"] == 15.0
    assert _value(app, "cel-2", condition="GD")["base"] == 15.0
    assert _value(app, "cel-2", condition="EX")["unit"] == 12.75
    assert _value(app, "cel-2", condition="GD")["unit"] == 10.5


def test_an_unpriced_printing_reports_no_base(app):
    v = _value(app, "bs-2")
    assert v["basis"] == "no_data"
    assert v["base"] is None


def test_pricing_the_reprint_leaves_the_other_printing_alone(app):
    """The regression: the €10 landed on bs-2 and cel-2 stayed unpriced."""
    client = app.test_client()
    r = client.put("/api/prices/manual/cel-2/normal", json={"price": 10})
    assert r.status_code == 200

    rows = {i["card_id"]: i for i in
            client.get("/api/collection/by-card/bs-2?reprints=1").get_json()["data"]}
    assert rows["cel-2"]["value"]["manual"] is True
    assert rows["cel-2"]["value"]["base"] == 10.0
    # Nothing was written against the card the modal was opened on.
    assert app.extensions["repo"].get_price("bs-2", "normal") is None


def test_clearing_it_hands_the_printing_back_to_the_feed(app):
    repo = app.extensions["repo"]
    repo.set_manual_price("cel-2", "normal", 10.0)
    assert _value(app, "cel-2")["manual"] is True
    app.test_client().put("/api/prices/manual/cel-2/normal", json={"price": None})
    assert repo.get_price("cel-2", "normal", source="manual") is None
