"""Multi-edition (printing) mapping."""
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
    for sid, name, date in [("base1", "Base", "1999/01/09"),
                            ("basep", "Wizards Black Star Promos", "1999/07/01"),
                            ("neo3", "Neo Revelation", "2001/09/21")]:
        r.upsert_official_set({"id": sid, "name": name, "series": "x",
                               "printed_total": 10, "total": 10, "release_date": date,
                               "ptcgo_code": None, "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard",
         "number": "4", "supertype": "Pokémon"},
        {"id": "basep-3", "official_set_id": "basep", "name": "Charizard",
         "number": "3", "supertype": "Pokémon"},
        {"id": "base1-31", "official_set_id": "base1", "name": "Jynx",
         "number": "31", "supertype": "Pokémon"},
        {"id": "neo3-31", "official_set_id": "neo3", "name": "Jynx",
         "number": "31", "supertype": "Pokémon"},
    ])
    yield r
    os.unlink(path)


def test_auto_detection_groups_same_name_and_number(repo):
    """The best structural signal the catalog offers. It is a hint, not truth —
    Jynx #31 in Base Set and Neo Revelation really are different cards, and this
    pairs them. Recorded as source='auto' so it can be told apart."""
    repo.rebuild_printings()
    jynx = repo.printings_for_card("base1-31")
    assert len(jynx) == 2
    assert {p["source"] for p in jynx} == {"auto"}


def test_different_numbers_are_not_auto_grouped(repo):
    """Charizard is #4 in Base Set and #3 as a promo, so the heuristic cannot
    see it. Only the user can say these are the same card."""
    repo.rebuild_printings()
    assert repo.printings_for_card("base1-4") == []


def test_slot_membership_defines_a_group_and_wins(repo):
    """Grouping cards in a personal set slot is a direct statement that they are
    the same logical card, so it is authoritative."""
    repo.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    repo.replace_rule_slots("mine", [
        {"position": 0, "label": "Charizard", "cards": ["base1-4", "basep-3"],
         "display_card_id": "base1-4"}])
    repo.rebuild_printings()

    printings = repo.printings_for_card("base1-4")
    assert [p["card_id"] for p in printings] == ["base1-4", "basep-3"]
    assert {p["source"] for p in printings} == {"slot"}
    assert [bool(p["is_reprint"]) for p in printings] == [False, True], \
        "earliest release is the original"


def test_rebuild_is_idempotent(repo):
    repo.rebuild_printings()
    first = repo.count_printings()
    repo.rebuild_printings()
    assert repo.count_printings() == first


def test_rebuild_preserves_manual_groups(repo):
    repo.rebuild_printings()
    with repo.tx() as c:
        c.execute("""INSERT INTO card_printings
                       (print_group, card_id, official_set_id, is_reprint,
                        display_name, source)
                     VALUES ('base1-4','base1-4','base1',0,'Hand made','manual')""")
    repo.rebuild_printings()
    assert repo._scalar(
        "SELECT COUNT(*) FROM card_printings WHERE source='manual'") == 1


def test_collection_item_records_the_printing(repo):
    repo.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    repo.replace_rule_slots("mine", [
        {"position": 0, "label": "Charizard", "cards": ["base1-4", "basep-3"],
         "display_card_id": "base1-4"}])
    repo.rebuild_printings()
    promo = [p for p in repo.printings_for_card("base1-4")
             if p["card_id"] == "basep-3"][0]

    item = repo.upsert_collection_item({"card_id": "basep-3",
                                        "printing_id": promo["id"]})
    assert item["printing_id"] == promo["id"]

    # and the Base Set slot is still completed by the promo copy
    assert repo.set_progress("mine")[0]["owned"] == 1
