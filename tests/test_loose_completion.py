"""Experimental: loose completion — any owned printing counts for a set.

With it on for Base Set, a Jungle Pikachu you hold fills the Base Set Pikachu
slot. Off (the default) only the set's own printing counts.
"""
import json

import pytest

from tombot.config import Config, DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "l.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db(DEFAULT_MODIFIERS)
    for sid, name, rel in (("bs", "Base Set", "1999/01/09"),
                           ("ju", "Jungle", "1999/06/16")):
        r.upsert_official_set({"id": sid, "name": name, "series": "Base",
                               "printed_total": 1, "total": 1, "release_date": rel,
                               "ptcgo_code": sid.upper(), "logo_url": None,
                               "symbol_url": None})
    # Same card (Pikachu) in both sets; a distractor (Clefable) only in Base.
    r.upsert_cards([
        {"id": "bs-58", "official_set_id": "bs", "name": "Pikachu", "number": "58",
         "rarity": "Common"},
        {"id": "bs-1", "official_set_id": "bs", "name": "Clefable", "number": "1",
         "rarity": "Rare Holo"},
        {"id": "ju-60", "official_set_id": "ju", "name": "Pikachu", "number": "60",
         "rarity": "Common"},
    ])
    r.upsert_collection_set({"id": "base", "name": "Base Set",
                             "rules_json": json.dumps({"include_sets": ["bs"]})})
    r.upsert_collection_set({"id": "jungle", "name": "Jungle",
                             "rules_json": json.dumps({"include_sets": ["ju"]})})
    for s in r.list_collection_sets():
        r._all  # noqa
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    for sid in ("base", "jungle"):
        a.extensions["setbuilder"].build(sid)
    # Own only the JUNGLE Pikachu.
    a.extensions["repo"].upsert_collection_item({"card_id": "ju-60"})
    return a


def _owned(app, set_id):
    return app.extensions["repo"].set_progress(set_id)[0]["owned"]


def test_strict_does_not_count_a_reprint(app):
    # Base Set: only Clefable + Pikachu slots; owning a Jungle Pikachu counts
    # for nothing here by default.
    assert _owned(app, "base") == 0


def test_loose_counts_the_reprint(app):
    app.extensions["repo"].set_loose_completion("base", True)
    assert _owned(app, "base") == 1          # the Jungle Pikachu fills Base's slot


def test_loose_is_per_set(app):
    app.extensions["repo"].set_loose_completion("base", True)
    # Jungle itself is unaffected — it owns its own Pikachu regardless.
    assert _owned(app, "jungle") == 1
    # A card with no reprint owned (Clefable) is still not counted for Base.
    assert app.extensions["repo"].set_progress("base")[0]["target"] == 2


def test_the_grid_marks_the_reprinted_card_owned_when_loose(app):
    repo = app.extensions["repo"]
    strict = {c["id"]: c["owned_qty"] for c in repo.set_cards_with_state("base")}
    assert strict["bs-58"] == 0 and strict["bs-1"] == 0
    repo.set_loose_completion("base", True)
    loose = {c["id"]: c["owned_qty"] for c in repo.set_cards_with_state("base")}
    assert loose["bs-58"] == 1               # Pikachu now shows owned
    assert loose["bs-1"] == 0                # Clefable still not


def test_endpoint_toggles_and_get_reports_it(app):
    client = app.test_client()
    assert client.get("/api/sets/base").get_json()["loose_completion"] is False
    r = client.put("/api/sets/base/loose", json={"enabled": True})
    assert r.status_code == 200 and r.get_json()["loose_completion"] is True
    assert client.get("/api/sets/base").get_json()["loose_completion"] is True
    client.put("/api/sets/base/loose", json={"enabled": False})
    assert client.get("/api/sets/base").get_json()["loose_completion"] is False
