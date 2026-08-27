"""The Cartas view: owned inventory vs every card in the personal sets."""
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
                           "printed_total": 4, "total": 4,
                           "release_date": "1999/01/09", "ptcgo_code": "BS",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-1", "official_set_id": "base1", "name": "Alakazam", "number": "1"},
        {"id": "base1-2", "official_set_id": "base1", "name": "Blastoise", "number": "2"},
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard", "number": "4"},
        {"id": "base4-4", "official_set_id": "base1", "name": "Charizard", "number": "4"},
    ])
    r.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    r.replace_rule_slots("mine", [
        {"position": 0, "label": "Alakazam", "cards": ["base1-1"], "display_card_id": "base1-1"},
        {"position": 1, "label": "Blastoise", "cards": ["base1-2"], "display_card_id": "base1-2"},
        # one slot grouping two printings — the duplicate-placeholder trap
        {"position": 2, "label": "Charizard", "cards": ["base1-4", "base4-4"],
         "display_card_id": "base1-4"},
    ])
    yield r
    os.unlink(path)


def test_all_mode_returns_a_row_per_slot_when_nothing_is_owned(repo):
    """A slot grouping several catalog cards must yield ONE placeholder, not one
    per member card — joining set_slot_cards directly would duplicate it."""
    rows, total = repo.list_slots_with_ownership(set_id="mine", page_size=100)
    assert total == 3
    assert [r["label"] for r in rows] == ["Alakazam", "Blastoise", "Charizard"]
    assert all(r["owned"] is False for r in rows)


def test_all_mode_marks_owned_rows(repo):
    repo.upsert_collection_item({"card_id": "base1-1"})
    repo.set_card_rating("base1-1", 8)
    rows, _ = repo.list_slots_with_ownership(set_id="mine", page_size=100)
    owned = {r["label"]: r["owned"] for r in rows}
    assert owned == {"Alakazam": True, "Blastoise": False, "Charizard": False}


def test_owning_any_member_of_a_grouped_slot_marks_it_owned(repo):
    """Owning the reprint satisfies the slot, which is the whole point of slots."""
    repo.upsert_collection_item({"card_id": "base4-4"})
    rows, _ = repo.list_slots_with_ownership(set_id="mine", page_size=100)
    assert {r["label"]: r["owned"] for r in rows}["Charizard"] is True


def test_multiple_owned_variants_produce_multiple_rows(repo):
    repo.upsert_collection_item({"card_id": "base1-1", "condition": "M/NM"})
    repo.upsert_collection_item({"card_id": "base1-1", "condition": "LP"})
    rows, total = repo.list_slots_with_ownership(set_id="mine", page_size=100)
    assert total == 4, "two owned variants + two placeholders"
    assert sum(1 for r in rows if r["label"] == "Alakazam") == 2


def test_physical_filters_exclude_placeholders(repo):
    """Condition, variant and language describe a copy in hand, so a placeholder
    cannot match them. The rank is deliberately NOT in this group — it belongs to
    the card, so an unacquired card can still carry one."""
    repo.upsert_collection_item({"card_id": "base1-1", "condition": "M/NM"})
    repo.upsert_collection_item({"card_id": "base1-2", "condition": "LP"})

    nm, _ = repo.list_slots_with_ownership(set_id="mine", condition="NM", page_size=100)
    assert [r["label"] for r in nm] == ["Alakazam"]
    assert all(r["owned"] for r in nm)


def test_rank_filter_is_not_a_physical_filter(repo):
    repo.upsert_collection_item({"card_id": "base1-1"})
    repo.set_card_rating("base1-1", 8)
    repo.set_card_rating("base1-2", 7)          # ranked, not owned

    top, _ = repo.list_slots_with_ownership(set_id="mine", rating_min=7, page_size=100)
    assert {r["label"] for r in top} == {"Alakazam", "Blastoise"}


def test_sorting_tolerates_placeholders(repo):
    """Ordering by an item column would scatter unowned rows unpredictably, so
    every sort falls back to a card column."""
    repo.upsert_collection_item({"card_id": "base1-2"})
    repo.set_card_rating("base1-2", 5)
    by_rating, _ = repo.list_slots_with_ownership(set_id="mine", sort="rating", page_size=100)
    assert by_rating[0]["label"] == "Blastoise", "ranked card first"
    assert len(by_rating) == 3, "placeholders still present"

    by_number, _ = repo.list_slots_with_ownership(set_id="mine", sort="number", page_size=100)
    assert [r["number"] for r in by_number] == ["1", "2", "4"]

    by_owned, _ = repo.list_slots_with_ownership(set_id="mine", sort="owned", page_size=100)
    assert by_owned[0]["owned"] is True


def test_all_mode_without_a_set_covers_every_personal_set(repo):
    repo.upsert_collection_set({"id": "other", "name": "Otro"})
    repo.replace_rule_slots("other", [
        {"position": 0, "label": "Alakazam", "cards": ["base1-1"], "display_card_id": "base1-1"}])
    _, total = repo.list_slots_with_ownership(page_size=100)
    assert total == 4, "3 slots in 'mine' + 1 in 'other'"


def test_ownership_totals(repo):
    repo.upsert_collection_item({"card_id": "base1-1"})
    assert repo.slots_ownership_totals("mine") == {"slots": 3, "owned_slots": 1}
