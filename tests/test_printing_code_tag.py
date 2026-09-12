"""The modal names the printing each copy is, e.g. FO-13 (#83).

The tag matters most on a grouped tile: one Dragonair tile can list a Base copy
and a Base Set 2 copy, and until now the two rows read identically — same
variant, same grade, same language. The set code is what tells them apart.
"""
import json

import pytest

from tombot.config import Config
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "p.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    r.upsert_official_set({"id": "fo", "name": "Fossil", "series": "Base",
                           "printed_total": 2, "total": 2, "release_date": "1999/10/10",
                           "ptcgo_code": "FO", "logo_url": None, "symbol_url": None})
    # A set tcggo sent no code for: the tag must still name the set, not vanish.
    r.upsert_official_set({"id": "b2", "name": "Base Set 2", "series": "Base",
                           "printed_total": 1, "total": 1, "release_date": "2000/02/24",
                           "ptcgo_code": "", "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "fo-13", "official_set_id": "fo", "name": "Muk", "number": "13",
         "rarity": "Rare Holo", "artist": "Kagemaru Himeno"},
        {"id": "fo-28", "official_set_id": "fo", "name": "Muk", "number": "28",
         "rarity": "Rare", "artist": "Kagemaru Himeno"},
        {"id": "b2-22", "official_set_id": "b2", "name": "Muk", "number": "22",
         "rarity": "Rare", "artist": "Kagemaru Himeno"},
    ])
    r.upsert_collection_set({"id": "fo-completo", "name": "Fossil",
                             "rules_json": json.dumps({"include_sets": ["fo"]})})
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.extensions["setbuilder"].build("fo-completo")
    a.extensions["repo"].upsert_collection_item(
        {"card_id": "fo-13", "variant": "holo", "condition": "GD", "language": "es"})
    return a


def test_a_copy_names_its_printing(app):
    item = app.extensions["repo"].items_by_card("fo-13")[0]
    assert item["set_code"] == "FO"
    assert f'{item["set_code"]}-{item["number"]}' == "FO-13"


def test_the_endpoint_carries_it(app):
    data = app.test_client().get("/api/cards/fo-13").get_json()
    assert data["items"][0]["set_code"] == "FO"


def test_a_reprint_row_names_its_own_set_not_the_cards(app):
    """The whole point: two rows in one modal, told apart by the code."""
    repo = app.extensions["repo"]
    repo.upsert_collection_item({"card_id": "b2-22", "variant": "normal",
                                 "condition": "GD", "language": "es"})
    rows = repo.items_by_card("fo-13", include_reprints=True)
    codes = sorted(f'{r["set_code"]}-{r["number"]}' for r in rows)
    assert codes == ["B2-22", "FO-13"]


def test_a_set_with_no_code_falls_back_to_its_id(app):
    """Base Set 2 has no ptcgo_code here; the tag still says which set it is."""
    repo = app.extensions["repo"]
    repo.upsert_collection_item({"card_id": "b2-22", "variant": "normal"})
    item = repo.items_by_card("b2-22")[0]
    assert item["set_code"] == "B2"
