"""The completion rules from spec §17 and §4 — the part the original schema got wrong.

Owning Charizard holo AND Charizard non-holo must count as ONE completed card,
while both still count as physical copies and both contribute to value.
"""
import json
import os
import tempfile

import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo, _number_sort


@pytest.fixture()
def repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = PokemonRepo(path)
    r.init_db(DEFAULT_MODIFIERS)
    r.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                           "printed_total": 102, "total": 102,
                           "release_date": "1999/01/09", "ptcgo_code": "BS",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard",
         "number": "4", "rarity": "Rare Holo"},
        {"id": "base1-10", "official_set_id": "base1", "name": "Mewtwo",
         "number": "10", "rarity": "Rare Holo"},
        {"id": "base1-2", "official_set_id": "base1", "name": "Blastoise",
         "number": "2", "rarity": "Rare Holo"},
    ])
    r.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    r.replace_rule_slots("mine", [
        {"position": 0, "label": "Blastoise", "cards": ["base1-2"], "display_card_id": "base1-2"},
        {"position": 1, "label": "Charizard", "cards": ["base1-4"], "display_card_id": "base1-4"},
        {"position": 2, "label": "Mewtwo", "cards": ["base1-10"], "display_card_id": "base1-10"},
    ])
    yield r
    os.unlink(path)


def test_two_variants_complete_one_slot(repo):
    """Spec §17: holo + non-holo Charizard = 1 completed card, 2 physical copies."""
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo", "quantity": 1})
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "normal", "quantity": 1})

    progress = repo.set_progress("mine")[0]
    assert progress["target"] == 3
    assert progress["owned"] == 1, "two variants of one card must complete one slot only"

    totals = repo.collection_totals()
    assert totals["unique_cards"] == 1
    assert totals["physical_cards"] == 2, "both variants still count as physical cards"


def test_quantity_adds_to_physical_not_to_completion(repo):
    """Spec §4: Charizard x3 = 1 completed card, 3 physical."""
    repo.upsert_collection_item({"card_id": "base1-4", "quantity": 3})
    assert repo.set_progress("mine")[0]["owned"] == 1
    assert repo.collection_totals()["physical_cards"] == 3


def test_duplicate_combination_increments_instead_of_duplicating(repo):
    """PLAN.md §2.5: without the unique constraint the physical count silently doubles."""
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo",
                                 "condition": "M/NM", "language": "es", "quantity": 1})
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo",
                                 "condition": "M/NM", "language": "es", "quantity": 2})
    assert repo.collection_totals()["item_rows"] == 1
    assert repo.collection_totals()["physical_cards"] == 3


def test_different_condition_is_a_separate_row(repo):
    """Condition affects value, so NM and LP must not be merged."""
    repo.upsert_collection_item({"card_id": "base1-4", "condition": "M/NM", "quantity": 1})
    repo.upsert_collection_item({"card_id": "base1-4", "condition": "LP", "quantity": 1})
    assert repo.collection_totals()["item_rows"] == 2
    assert repo.set_progress("mine")[0]["owned"] == 1


def test_merged_slot_accepts_any_member(repo):
    """A reprint grouped into one slot is completed by owning either printing."""
    repo.replace_rule_slots("mine", [
        {"position": 0, "label": "Charizard", "cards": ["base1-4", "base1-2"],
         "display_card_id": "base1-4"},
    ])
    assert repo.set_progress("mine")[0]["target"] == 1
    repo.upsert_collection_item({"card_id": "base1-2", "quantity": 1})
    assert repo.set_progress("mine")[0]["owned"] == 1


def test_missing_list_excludes_owned(repo):
    repo.upsert_collection_item({"card_id": "base1-4", "quantity": 1})
    missing = repo.missing_slots("mine")
    assert {m["card_id"] for m in missing} == {"base1-2", "base1-10"}


def test_number_sort_is_numeric(repo):
    """'10' must not sort before '2'; promos sort after plain numbers."""
    assert _number_sort("2") < _number_sort("10")
    assert _number_sort("10") < _number_sort("H12")


def test_foreign_keys_enforced(repo):
    """SQLite defaults foreign_keys OFF; the repo must turn it on."""
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        repo.upsert_collection_item({"card_id": "does-not-exist", "quantity": 1})


def test_rebuild_preserves_manual_slots(repo):
    """PLAN.md §2.10: a catalog-driven rebuild must not wipe hand curation."""
    with repo.tx() as c:
        # the user moves base1-10 out of its rule slot into a hand-made one
        c.execute("DELETE FROM set_slots WHERE set_id='mine' AND display_card_id='base1-10'")
        cur = c.execute("INSERT INTO set_slots(set_id,position,label,display_card_id,source) "
                        "VALUES ('mine',99,'Manual','base1-10','manual')")
        c.execute("INSERT INTO set_slot_cards(slot_id,card_id,set_id) VALUES (?,?,?)",
                  (cur.lastrowid, "base1-10", "mine"))
    # a rebuild proposes base1-10 again; it must NOT clobber the manual slot
    repo.replace_rule_slots("mine", [
        {"position": 0, "label": "Charizard", "cards": ["base1-4"], "display_card_id": "base1-4"},
        {"position": 1, "label": "Mewtwo", "cards": ["base1-10"], "display_card_id": "base1-10"},
    ])
    slots = repo.get_set_slots("mine")
    manual = [s for s in slots if s["source"] == "manual"]
    assert len(manual) == 1 and manual[0]["label"] == "Manual"
    assert len(slots) == 2, "rule rebuild must skip cards already held by a manual slot"


def test_market_url_prefers_resolved_direct_link(repo):
    """PLAN.md §2.17: the payload's cardmarket.url is a redirector, not a
    Cardmarket address. Once resolved, the direct URL must win."""
    from tombot.services.market import market_url

    card = repo.get_card("base1-4")
    assert market_url(card) == "https://prices.pokemontcg.io/cardmarket/base1-4", \
        "unresolved cards must still yield a working link"

    repo.set_card_market_url(
        "base1-4",
        "https://cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charizard-V2-BS4")
    card = repo.get_card("base1-4")
    url = market_url(card, locale="es")
    assert url == ("https://cardmarket.com/es/Pokemon/Products/Singles/"
                   "Base-Set/Charizard-V2-BS4")


def test_market_urls_written_in_one_transaction(repo):
    """Committing per card starves concurrent readers over a 1100-card run."""
    pairs = [("base1-4", "https://cardmarket.com/en/a"),
             ("base1-2", "https://cardmarket.com/en/b")]
    assert repo.set_card_market_urls(pairs) == 2
    assert repo.count_market_urls() == 2


def test_nested_tx_does_not_commit_early(repo):
    """get_collection_item calls get_photos; a nested block must join the outer
    transaction, not commit half of it."""
    import sqlite3
    try:
        with repo.tx() as c:
            c.execute("INSERT INTO collection_items(card_id, quantity) VALUES ('base1-4', 1)")
            with repo.tx() as inner:
                inner.execute("SELECT 1")          # nested read must not commit
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert repo.collection_totals()["item_rows"] == 0, "outer rollback must undo everything"


def test_partial_catalog_is_not_treated_as_complete(repo):
    """A half-imported catalog must be detected as incomplete.

    The original guard asked "are there any cards at all", so an import that
    salvaged one set out of twelve — routine when the upstream is throwing
    500s — permanently suppressed every later retry, and the install could
    never repair itself.
    """
    # base1 is imported but short: the fixture loaded 3 cards, the set has 102.
    gaps = repo.catalog_gaps(["base1"])
    assert len(gaps) == 1
    assert gaps[0]["set"] == "base1"
    assert gaps[0]["why"] == "incomplete"
    assert gaps[0]["have"] == 3 and gaps[0]["expected"] == 102


def test_never_imported_set_is_a_gap(repo):
    gaps = repo.catalog_gaps(["base1", "gym1"])
    assert {g["set"]: g["why"] for g in gaps}["gym1"] == "never imported"


def test_complete_set_is_not_a_gap(repo):
    """Guard against the opposite failure: re-importing a complete catalog on
    every start would hammer a flaky upstream for no reason."""
    with repo.tx() as c:
        c.execute("UPDATE official_sets SET total = 3 WHERE id = 'base1'")
    assert repo.catalog_gaps(["base1"]) == []
