"""Target quantity: how many copies of a card count as complete."""
import os
import tempfile

import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = PokemonRepo(path)
    r.init_db(DEFAULT_MODIFIERS)
    r.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                           "printed_total": 2, "total": 2,
                           "release_date": "1999/01/09", "ptcgo_code": None,
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard", "number": "4"},
        {"id": "base1-2", "official_set_id": "base1", "name": "Blastoise", "number": "2"},
    ])
    r.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    r.replace_rule_slots("mine", [
        {"position": 0, "label": "Blastoise", "cards": ["base1-2"], "display_card_id": "base1-2"},
        {"position": 1, "label": "Charizard", "cards": ["base1-4"], "display_card_id": "base1-4"},
    ])
    yield r
    os.unlink(path)


def test_default_target_is_one_and_stores_no_row(repo):
    """The default must cost nothing and behave exactly as before targets existed."""
    assert repo.get_card_target("base1-4") == 1
    repo.set_card_target("base1-4", 1)
    assert repo._scalar("SELECT COUNT(*) FROM card_targets") == 0


def test_holding_fewer_than_the_target_leaves_the_slot_incomplete(repo):
    repo.upsert_collection_item({"card_id": "base1-4", "quantity": 1})
    assert repo.set_progress("mine")[0]["owned"] == 1

    repo.set_card_target("base1-4", 3)
    assert repo.set_progress("mine")[0]["owned"] == 0
    slot = next(s for s in repo.get_set_slots("mine") if s["label"] == "Charizard")
    assert bool(slot["owned"]) is False
    assert slot["quantity"] == 1 and slot["target"] == 3


def test_reaching_the_target_completes_the_slot(repo):
    repo.set_card_target("base1-4", 3)
    repo.upsert_collection_item({"card_id": "base1-4", "quantity": 3})
    assert repo.set_progress("mine")[0]["owned"] == 1


def test_copies_count_across_variants(repo):
    """Three copies is three copies, however they are split across rows."""
    repo.set_card_target("base1-4", 3)
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo", "quantity": 1})
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "normal", "quantity": 2})
    assert repo.set_progress("mine")[0]["owned"] == 1


def test_missing_list_reports_the_shortfall(repo):
    """The wishlist needs the number still to buy, not just that something is short."""
    repo.set_card_target("base1-4", 4)
    repo.upsert_collection_item({"card_id": "base1-4", "quantity": 1})
    row = next(m for m in repo.missing_slots("mine") if m["label"] == "Charizard")
    assert row["target"] == 4 and row["held"] == 1 and row["still_needed"] == 3


def test_a_card_held_but_under_target_still_appears_as_missing(repo):
    repo.set_card_target("base1-4", 2)
    repo.upsert_collection_item({"card_id": "base1-4", "quantity": 1})
    assert "Charizard" in {m["label"] for m in repo.missing_slots("mine")}


def test_target_below_one_is_rejected_by_the_database(repo):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        with repo.tx() as c:
            c.execute("INSERT INTO card_targets(card_id, target) VALUES ('base1-4', 0)")
