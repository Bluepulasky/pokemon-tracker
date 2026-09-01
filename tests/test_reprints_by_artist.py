"""Reprints are matched by name + artist, not name alone (issue #47).

The Base Set Magneton and the Fossil Magneton share a name but not an
illustrator, and a reprint reuses the artwork. So owning one must not count as
owning the other under loose completion, and the version picker opened on one
must not list the other. The Fossil and Legendary Collection Magnetons share
both name and illustrator (Ken Sugimori) — those are real reprints.
"""
import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.artist_backfill import scan_cache_for_artists
from tombot.services.repository import PokemonRepo
from tombot.services.setbuilder import SetBuilder


def _prod(pid, card_id, code, number, artist):
    return {"product_id": pid, "episode_id": 1, "card_id": card_id, "code": code,
            "number": number, "name": "Magneton", "version": "Unlimited",
            "rarity": "Rare", "currency": "EUR", "price": 5.0, "price_low": None,
            "price_avg30": None, "price_avg7": None, "available": 1, "image": None,
            "market_url": f"https://x/{pid}", "artist": artist}


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "r.db")
    r.init_db(DEFAULT_MODIFIERS)
    for sid, name, rd in [("bs", "Base Set", "1999/01/09"),
                          ("fo", "Fossil", "1999/10/10"),
                          ("lc", "Legendary Collection", "2002/05/24")]:
        r.upsert_official_set({"id": sid, "name": name, "series": "",
                               "printed_total": 1, "total": 1, "release_date": rd,
                               "ptcgo_code": sid.upper(), "logo_url": None,
                               "symbol_url": None})
    r.upsert_cards([
        {"id": "bs-9", "official_set_id": "bs", "name": "Magneton", "number": "9",
         "rarity": "Rare Holo", "artist": "Keiji Kinebuchi"},
        {"id": "fo-26", "official_set_id": "fo", "name": "Magneton", "number": "26",
         "rarity": "Rare", "artist": "Ken Sugimori"},
        {"id": "lc-28", "official_set_id": "lc", "name": "Magneton", "number": "28",
         "rarity": "Rare", "artist": "Ken Sugimori"},
    ])
    r.upsert_market_products([
        _prod(101, "bs-9", "BS 9", "9", "Keiji Kinebuchi"),
        _prod(102, "fo-26", "FO 26", "26", "Ken Sugimori"),
        _prod(103, "lc-28", "LC 28", "28", "Ken Sugimori"),
    ])
    return r


def _fossil_goal(repo):
    repo.upsert_collection_set({"id": "fossil", "name": "Fossil",
                               "rules_json": '{"include_sets": ["fo"]}'})
    SetBuilder(repo).build("fossil")
    repo.set_loose_completion("fossil", True)


def test_a_non_reprint_does_not_count_under_loose(repo):
    """Base Set Magneton (Kinebuchi) must NOT fill the Fossil slot (issue #47)."""
    _fossil_goal(repo)
    repo.upsert_collection_item({"card_id": "bs-9", "variant": "holo"})
    assert repo.set_progress("fossil")[0]["owned"] == 0
    grid = {c["id"]: c["owned_qty"] for c in repo.set_cards_with_state("fossil")}
    assert grid["fo-26"] == 0


def test_a_real_reprint_counts_under_loose(repo):
    """Legendary Collection Magneton (Sugimori) IS a reprint of the Fossil one."""
    _fossil_goal(repo)
    repo.upsert_collection_item({"card_id": "lc-28"})
    assert repo.set_progress("fossil")[0]["owned"] == 1
    grid = {c["id"]: c["owned_qty"] for c in repo.set_cards_with_state("fossil")}
    assert grid["fo-26"] == 1


def test_strict_completion_ignores_artist(repo):
    """With loose off, only the set's own card counts — the reprint does not."""
    repo.upsert_collection_set({"id": "fossil", "name": "Fossil",
                               "rules_json": '{"include_sets": ["fo"]}'})
    SetBuilder(repo).build("fossil")
    repo.upsert_collection_item({"card_id": "lc-28"})   # a reprint, not the Fossil card
    assert repo.set_progress("fossil")[0]["owned"] == 0


def test_the_picker_lists_only_real_reprints(repo):
    """The version list for the Fossil Magneton is Fossil + LC, not Base Set."""
    got = repo.market_products_for_reprint("fo-26")
    assert {r["set_id"] for r in got} == {"fo", "lc"}


def _fossil_goal_strict(repo):
    repo.upsert_collection_set({"id": "fossil", "name": "Fossil",
                               "rules_json": '{"include_sets": ["fo"]}'})
    SetBuilder(repo).build("fossil")


# -------- issue #47 point 2: the modal reflects loose ownership --------------
def test_modal_shows_owned_reprints_when_loose(repo):
    """Opening the Fossil Magneton, with Fossil loose, shows the owned LC one."""
    _fossil_goal(repo)                                   # loose on
    repo.upsert_collection_item({"card_id": "lc-28"})    # own the reprint
    rows = repo.items_by_card("fo-26")
    assert len(rows) == 1
    assert rows[0]["card_id"] == "lc-28" and rows[0]["is_reprint"] is True


def test_modal_stays_strict_without_loose(repo):
    """Without loose, the modal for a card you don't own shows nothing."""
    _fossil_goal_strict(repo)                            # loose off
    repo.upsert_collection_item({"card_id": "lc-28"})
    assert repo.items_by_card("fo-26") == []


# -------- issue #47 point 3: the Cartas set-filter reflects loose ------------
def test_cartas_filter_includes_reprints_when_loose(repo):
    _fossil_goal(repo)                                   # loose on
    repo.upsert_collection_item({"card_id": "lc-28"})
    rows, total = repo.list_collection(set_id="fossil")
    assert total == 1 and rows[0]["card_id"] == "lc-28"


def test_cartas_filter_stays_strict_without_loose(repo):
    _fossil_goal_strict(repo)                            # loose off
    repo.upsert_collection_item({"card_id": "lc-28"})
    _, total = repo.list_collection(set_id="fossil")
    assert total == 0


def test_backfill_scan_reads_artist_from_cache(tmp_path, monkeypatch):
    """The backfill recovers illustrators from cached tcggo responses, no network."""
    import json
    # Run from an empty cwd so the scan's cwd-relative fallback dirs (which would
    # otherwise resolve to the repo's own cache) find nothing but this fixture.
    monkeypatch.chdir(tmp_path)
    cache = tmp_path / ".cache-tcggo"
    cache.mkdir()
    (cache / "a.json").write_text(json.dumps({"data": [
        {"cardmarket_id": 101, "name": "Magneton",
         "artist": {"id": 605, "name": "Keiji Kinebuchi"}},
        {"cardmarket_id": 102, "name": "Magneton", "artist": "Ken Sugimori"},
    ]}))
    got = scan_cache_for_artists(tmp_path)
    assert got == {101: "Keiji Kinebuchi", 102: "Ken Sugimori"}
