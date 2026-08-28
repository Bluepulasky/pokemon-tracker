"""The collection rule is an editable call on the set, separate from the set.

The catalogue is always the whole set; the mode (all / sin holos / solo holos)
decides which part of it you are trying to complete. Switching it
re-materialises the slots without touching the imported cards.
"""
import json

import pytest

from tombot.config import DEFAULT_MODIFIERS, Config
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "m.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    repo = PokemonRepo(Config.DB_PATH)
    repo.init_db(DEFAULT_MODIFIERS)
    repo.upsert_official_set({"id": "ju", "name": "Jungle", "series": "Base",
                              "printed_total": 4, "total": 4,
                              "release_date": "1999/06/16", "ptcgo_code": "JU",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([
        {"id": "ju-1", "official_set_id": "ju", "name": "Clefable", "number": "1",
         "rarity": "Rare Holo"},
        {"id": "ju-2", "official_set_id": "ju", "name": "Electrode", "number": "2",
         "rarity": "Rare Holo"},
        {"id": "ju-20", "official_set_id": "ju", "name": "Cleffa", "number": "20",
         "rarity": "Common"},
        {"id": "ju-21", "official_set_id": "ju", "name": "Pidgey", "number": "21",
         "rarity": "Common"},
    ])
    repo.upsert_collection_set({"id": "mi-jungle", "name": "Jungle",
                                "rules_json": json.dumps({"include_sets": ["ju"]})})
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    return a


def _slots(app):
    return {s["card_id"] for s in app.extensions["repo"].get_set_slots("mi-jungle")}


def test_default_mode_collects_the_whole_set(app):
    app.extensions["setbuilder"].build("mi-jungle")
    body = app.test_client().get("/api/sets/mi-jungle/mode").get_json()
    assert body["mode"] == "all"


def test_no_holos_drops_the_holos(app):
    app.test_client().put("/api/sets/mi-jungle/mode", json={"mode": "no-holos"})
    assert _slots(app) == {"ju-20", "ju-21"}


def test_holos_only_keeps_only_holos(app):
    app.test_client().put("/api/sets/mi-jungle/mode", json={"mode": "holos-only"})
    assert _slots(app) == {"ju-1", "ju-2"}


def test_switching_back_to_all_restores_everything(app):
    client = app.test_client()
    client.put("/api/sets/mi-jungle/mode", json={"mode": "no-holos"})
    client.put("/api/sets/mi-jungle/mode", json={"mode": "all"})
    assert _slots(app) == {"ju-1", "ju-2", "ju-20", "ju-21"}


def test_the_set_of_cards_is_untouched_by_the_mode(app):
    """Changing the rule must never change the catalogue behind it."""
    repo = app.extensions["repo"]
    before = {c["id"] for c in repo._all("SELECT id FROM cards WHERE official_set_id='ju'")}
    app.test_client().put("/api/sets/mi-jungle/mode", json={"mode": "holos-only"})
    after = {c["id"] for c in repo._all("SELECT id FROM cards WHERE official_set_id='ju'")}
    assert before == after == {"ju-1", "ju-2", "ju-20", "ju-21"}


def test_an_unknown_mode_is_refused(app):
    r = app.test_client().put("/api/sets/mi-jungle/mode", json={"mode": "purple"})
    assert r.status_code == 400
