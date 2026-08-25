"""The app builds and its endpoints respond.

Every other test exercises the repository directly, so a syntax error or a bad
import in the API layer passed the whole suite unnoticed — which is exactly what
happened resolving a merge conflict in tombot/api/catalog.py. These tests import
the app, so that class of breakage fails loudly.
"""
import os
import tempfile

import pytest

from tombot.config import DEFAULT_MODIFIERS, Config
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "smoke.db"
    monkeypatch.setattr(Config, "DB_PATH", db)
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(Config, "CATALOG_IMG_DIR", tmp_path / "media" / "catalog")
    monkeypatch.setattr(Config, "COLLECTION_IMG_DIR", tmp_path / "media" / "collection")
    monkeypatch.setattr(Config, "THUMB_DIR", tmp_path / "media" / "thumbs")

    repo = PokemonRepo(db)
    repo.init_db(DEFAULT_MODIFIERS)
    repo.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                              "printed_total": 1, "total": 1,
                              "release_date": "1999/01/09", "ptcgo_code": None,
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "base1-4", "official_set_id": "base1",
                        "name": "Charizard", "number": "4", "rarity": "Rare Holo"}])
    repo.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    repo.replace_rule_slots("mine", [
        {"position": 0, "label": "Charizard", "cards": ["base1-4"],
         "display_card_id": "base1-4"}])

    from tombot import create_app
    app = create_app(Config)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize("path", [
    "/api/healthz", "/api/meta", "/api/cards", "/api/cards/base1-4",
    "/api/sets", "/api/sets/mine", "/api/sets/mine/missing",
    "/api/collection", "/api/collection?show_all=1",
    "/api/collection/by-card/base1-4", "/api/dashboard", "/api/stats/history",
    "/api/search?q=Charizard", "/api/prices/base1-4", "/api/prices/modifiers",
])
def test_endpoint_responds(client, path):
    assert client.get(path).status_code == 200, path


def test_card_detail_carries_both_rating_and_printings(client):
    """The two features that collided in a merge — a regression here is what the
    conflict resolution could plausibly have dropped."""
    card = client.get("/api/cards/base1-4").get_json()
    assert "rating" in card
    assert "available_printings" in card
    assert card["available_printings"], "a card with no siblings still gets one printing"
    assert "variants" in card["available_printings"][0]


def test_rating_round_trips_through_the_api(client):
    assert client.put("/api/cards/base1-4/rating", json={"rating": 7}).status_code == 200
    assert client.get("/api/cards/base1-4").get_json()["rating"] == 7


def test_invalid_rating_is_rejected(client):
    r = client.put("/api/cards/base1-4/rating", json={"rating": 99})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "invalid_rating"
