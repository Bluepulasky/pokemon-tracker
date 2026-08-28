"""Cards a set's rule removes must still be visible somewhere (issue #35).

Metal Energy was reported missing. It was not missing: Neo Genesis has 111
cards and 19 Rare Holo, and the set's rule excludes that rarity. The rule was
right, and the card was unreachable from every screen — which is the same thing
as missing, from where the user stands.

The fix is that the set view now shows the *whole* set: every card appears in
the grid, and a card the rule leaves out is simply flagged `collecting == 0`
(dimmed, with a hollow star) instead of vanishing. So the test is that the
endpoint carries every card with that flag, not a separate "excluded" list.
"""
import json

import pytest

from tombot.config import Config, DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "x.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db(DEFAULT_MODIFIERS)
    r.upsert_official_set({"id": "ng", "name": "Neo Genesis", "series": "Neo",
                           "printed_total": 4, "total": 4,
                           "release_date": "2000/12/16", "ptcgo_code": "NG",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "ng-9", "official_set_id": "ng", "name": "Lugia",
         "number": "9", "rarity": "Rare Holo"},
        {"id": "ng-19", "official_set_id": "ng", "name": "Metal Energy",
         "number": "19", "rarity": "Rare Holo"},
        {"id": "ng-20", "official_set_id": "ng", "name": "Cleffa",
         "number": "20", "rarity": "Rare"},
        {"id": "ng-21", "official_set_id": "ng", "name": "Donphan",
         "number": "21", "rarity": "Rare"},
    ])
    r.upsert_collection_set({"id": "ng-no-holos", "name": "Neo Genesis",
                             "rules_json": json.dumps(
                                 {"include_sets": ["ng"],
                                  "exclude_rarities": ["Rare Holo"]})})
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.extensions["setbuilder"].build("ng-no-holos")
    return a


def _cards(app):
    body = app.test_client().get("/api/sets/ng-no-holos").get_json()
    return {c["id"]: c for c in body["cards"]}


def test_the_rule_is_working_correctly(app):
    """Establish the premise: the card is in the catalogue and out of the goal."""
    repo = app.extensions["repo"]
    assert repo.get_card("ng-19") is not None
    assert {s["card_id"] for s in repo.get_set_slots("ng-no-holos")} == {"ng-20", "ng-21"}


def test_the_whole_set_is_carried_not_just_the_slots(app):
    """The view shows all four cards, so nothing the rule drops disappears."""
    body = app.test_client().get("/api/sets/ng-no-holos").get_json()
    assert len(body["slots"]) == 2
    assert [c["name"] for c in body["cards"]] == \
        ["Lugia", "Metal Energy", "Cleffa", "Donphan"]


def test_the_excluded_holos_are_flagged_not_hidden(app):
    """Metal Energy is present, just marked not-collecting — visible, not missing."""
    cards = _cards(app)
    assert cards["ng-9"]["collecting"] == 0 and cards["ng-19"]["collecting"] == 0
    assert cards["ng-20"]["collecting"] == 1 and cards["ng-21"]["collecting"] == 1


def test_cards_come_back_in_set_order(app):
    body = app.test_client().get("/api/sets/ng-no-holos").get_json()
    assert [c["number"] for c in body["cards"]] == ["9", "19", "20", "21"]


def test_a_hand_built_set_carries_no_cards(app):
    """No source sets means nothing to show, not an error."""
    app.extensions["repo"].upsert_collection_set(
        {"id": "hand", "name": "A mano", "rules_json": "{}"})
    body = app.test_client().get("/api/sets/hand").get_json()
    assert body["cards"] == []
