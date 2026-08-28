"""The set view shows the whole set with a per-card collecting toggle.

The rule (sin holos / todas) decides most of the set by rarity, but the view
shows every card either way — dimmed when it is not part of the goal — and a
star on each card forces it in or out regardless of the rule. That per-card
override is how a Rare Holo you actually want (Neo Genesis Metal Energy, and
here Jungle Clefable) gets collected under "sin holos".
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
    a.extensions["setbuilder"].build("mi-jungle")
    return a


def _cards(app):
    """card id -> row, from what the set view is served."""
    body = app.test_client().get("/api/sets/mi-jungle").get_json()
    return {c["id"]: c for c in body["cards"]}


# ------------------------------------------------------------ the whole set
def test_view_shows_every_card_not_just_the_slots(app):
    app.test_client().put("/api/sets/mi-jungle/mode", json={"mode": "no-holos"})
    cards = _cards(app)
    # sin holos collects only the two commons, but all four still show
    assert set(cards) == {"ju-1", "ju-2", "ju-20", "ju-21"}
    assert cards["ju-1"]["collecting"] == 0 and cards["ju-2"]["collecting"] == 0
    assert cards["ju-20"]["collecting"] == 1 and cards["ju-21"]["collecting"] == 1


def test_owned_qty_is_independent_of_collecting(app):
    """You can own a card the rule is not collecting."""
    app.test_client().put("/api/sets/mi-jungle/mode", json={"mode": "no-holos"})
    app.extensions["repo"].upsert_collection_item({"card_id": "ju-1", "quantity": 2})
    cards = _cards(app)
    assert cards["ju-1"]["owned_qty"] == 2
    assert cards["ju-1"]["collecting"] == 0  # owned but not a goal


# ---------------------------------------------------- the per-card override
def test_keep_forces_a_holo_in_under_sin_holos(app):
    """The Metal Energy / Clefable case."""
    client = app.test_client()
    client.put("/api/sets/mi-jungle/mode", json={"mode": "no-holos"})
    r = client.put("/api/sets/mi-jungle/card/ju-1", json={"action": "keep"})
    assert r.status_code == 200
    assert r.get_json()["slots"] == 3  # two commons + the forced-in holo
    assert _cards(app)["ju-1"]["collecting"] == 1


def test_drop_forces_a_card_out(app):
    client = app.test_client()
    client.put("/api/sets/mi-jungle/card/ju-20", json={"action": "drop"})
    assert _cards(app)["ju-20"]["collecting"] == 0
    # the other three are untouched
    assert _cards(app)["ju-21"]["collecting"] == 1


def test_reset_returns_a_card_to_the_rule(app):
    client = app.test_client()
    client.put("/api/sets/mi-jungle/mode", json={"mode": "no-holos"})
    client.put("/api/sets/mi-jungle/card/ju-1", json={"action": "keep"})
    client.put("/api/sets/mi-jungle/card/ju-1", json={"action": "reset"})
    assert _cards(app)["ju-1"]["collecting"] == 0  # back to what sin holos says


def test_override_survives_a_mode_change(app):
    """A per-card exception is not lost when the rarity rule is switched."""
    client = app.test_client()
    client.put("/api/sets/mi-jungle/card/ju-20", json={"action": "drop"})
    client.put("/api/sets/mi-jungle/mode", json={"mode": "all"})
    # 'all' would collect ju-20, but the explicit drop still wins
    assert _cards(app)["ju-20"]["collecting"] == 0


def test_unknown_card_is_404(app):
    r = app.test_client().put("/api/sets/mi-jungle/card/ju-999", json={"action": "keep"})
    assert r.status_code == 404


def test_bad_action_is_400(app):
    r = app.test_client().put("/api/sets/mi-jungle/card/ju-1", json={"action": "maybe"})
    assert r.status_code == 400
