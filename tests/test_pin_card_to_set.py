"""Pinning a card into a set by hand (issue #35).

A rule cannot say "everything except the holos, but keep this one". Neo Genesis
Metal Energy is a Rare Holo, so "sin holos" drops it — correctly by the rule
and wrongly by intent. The card is pinned rather than the rule bent.
"""
import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo
from tombot.services.setbuilder import SetBuilder


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "p.db")
    r.init_db(DEFAULT_MODIFIERS)
    r.upsert_official_set({"id": "ng", "name": "Neo Genesis", "series": "Neo",
                           "printed_total": 3, "total": 3,
                           "release_date": "2000/12/16", "ptcgo_code": "NG",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "ng-19", "official_set_id": "ng", "name": "Metal Energy",
         "number": "19", "rarity": "Rare Holo"},
        {"id": "ng-20", "official_set_id": "ng", "name": "Cleffa",
         "number": "20", "rarity": "Rare"},
        {"id": "ng-21", "official_set_id": "ng", "name": "Donphan",
         "number": "21", "rarity": "Rare"},
    ])
    import json
    r.upsert_collection_set({"id": "ng-no-holos", "name": "Neo Genesis (sin holos)",
                             "rules_json": json.dumps(
                                 {"include_sets": ["ng"],
                                  "exclude_rarities": ["Rare Holo"]})})
    SetBuilder(r).build("ng-no-holos")
    return r


def test_the_rule_really_does_exclude_it(repo):
    """The card is not missing from the catalogue — the rule leaves it out."""
    assert repo.get_card("ng-19") is not None
    slots = repo.get_set_slots("ng-no-holos")
    assert len(slots) == 2
    assert "ng-19" not in {s["card_id"] for s in slots}


def test_pinning_puts_it_in_the_set(repo):
    added = repo.add_manual_slot("ng-no-holos", "ng-19")

    assert added["card_id"] == "ng-19"
    slots = repo.get_set_slots("ng-no-holos")
    assert len(slots) == 3
    assert "ng-19" in {s["card_id"] for s in slots}


def test_a_rebuild_leaves_a_pinned_card_alone(repo):
    """The whole point: hand curation must survive a catalogue refresh."""
    repo.add_manual_slot("ng-no-holos", "ng-19")

    SetBuilder(repo).build("ng-no-holos")

    slots = repo.get_set_slots("ng-no-holos")
    assert "ng-19" in {s["card_id"] for s in slots}, \
        "a rebuild must not undo what someone pinned"
    assert len(slots) == 3


def test_pinning_twice_is_refused(repo):
    repo.add_manual_slot("ng-no-holos", "ng-19")
    assert repo.add_manual_slot("ng-no-holos", "ng-19") is None


def test_a_card_the_rule_already_covers_is_not_duplicated(repo):
    assert repo.add_manual_slot("ng-no-holos", "ng-20") is None
    assert len(repo.get_set_slots("ng-no-holos")) == 2


def test_unpinning_removes_it(repo):
    repo.add_manual_slot("ng-no-holos", "ng-19")
    assert repo.remove_manual_slot("ng-no-holos", "ng-19") is True
    assert "ng-19" not in {s["card_id"] for s in repo.get_set_slots("ng-no-holos")}


def test_a_rule_built_slot_cannot_be_unpinned(repo):
    """Only what a person added by hand can be removed by hand."""
    assert repo.remove_manual_slot("ng-no-holos", "ng-20") is False
    assert len(repo.get_set_slots("ng-no-holos")) == 2


def test_the_card_reports_which_sets_it_counts_for(repo):
    """Absence looks identical to non-existence until you can see this."""
    assert repo.sets_containing_card("ng-19") == []

    repo.add_manual_slot("ng-no-holos", "ng-19")

    rows = repo.sets_containing_card("ng-19")
    assert [r["id"] for r in rows] == ["ng-no-holos"]
    assert rows[0]["source"] == "manual"
    assert repo.sets_containing_card("ng-20")[0]["source"] == "rule"
