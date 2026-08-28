"""Cards a set's rule removes must still be visible somewhere (issue #35).

Metal Energy was reported missing. It was not missing: Neo Genesis has 111
cards and 19 Rare Holo, and the set's rule excludes that rarity. The rule was
right, and the card was unreachable from every screen — which is the same thing
as missing, from where the user stands.
"""
import json

import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo
from tombot.services.setbuilder import SetBuilder


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "x.db")
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
    r.upsert_collection_set({"id": "ng-no-holos", "name": "Neo Genesis (sin holos)",
                             "rules_json": json.dumps(
                                 {"include_sets": ["ng"],
                                  "exclude_rarities": ["Rare Holo"]})})
    SetBuilder(r).build("ng-no-holos")
    return r


def test_the_rule_is_working_correctly(repo):
    """Establish the premise: the card is in the catalogue and out of the set."""
    assert repo.get_card("ng-19") is not None
    assert {s["card_id"] for s in repo.get_set_slots("ng-no-holos")} == {"ng-20", "ng-21"}


def test_the_excluded_cards_are_reported(repo):
    excluded = repo.cards_excluded_from_set("ng-no-holos")

    assert [c["id"] for c in excluded] == ["ng-9", "ng-19"]
    assert all(c["rarity"] == "Rare Holo" for c in excluded)


def test_they_come_back_in_set_order(repo):
    """#9 before #19, so the list reads like the set rather than like a dump."""
    assert [c["number"] for c in repo.cards_excluded_from_set("ng-no-holos")] == ["9", "19"]


def test_a_set_with_no_exclusions_reports_none(repo):
    repo.upsert_collection_set({"id": "ng-full", "name": "Neo Genesis",
                                "rules_json": json.dumps({"include_sets": ["ng"]})})
    SetBuilder(repo).build("ng-full")

    assert repo.cards_excluded_from_set("ng-full") == []


def test_a_set_built_by_hand_reports_none(repo):
    """No source sets means nothing to compare against, not an error."""
    repo.upsert_collection_set({"id": "hand", "name": "A mano", "rules_json": "{}"})
    assert repo.cards_excluded_from_set("hand") == []


def test_an_unknown_set_reports_none(repo):
    assert repo.cards_excluded_from_set("does-not-exist") == []


def test_the_endpoint_carries_them(tmp_path, monkeypatch, repo):
    """The view needs them on the set, or the filter has nothing to show."""
    from tombot.config import Config

    for attr, value in (("DB_PATH", tmp_path / "x.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    from tombot import create_app
    client = create_app(Config).test_client()

    body = client.get("/api/sets/ng-no-holos").get_json()

    assert len(body["slots"]) == 2
    assert [c["name"] for c in body["excluded"]] == ["Lugia", "Metal Energy"]
