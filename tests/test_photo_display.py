"""Which photo represents a card in the grid."""
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
                           "printed_total": 102, "total": 102,
                           "release_date": "1999/01/09", "ptcgo_code": None,
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-12", "official_set_id": "base1", "name": "Ninetales", "number": "12"},
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard", "number": "4"},
    ])
    yield r
    os.unlink(path)


def _photo(repo, item_id, name):
    return repo.add_photo(item_id, {"filename": f"collection/{name}",
                                    "thumb_filename": f"thumbs/{name}",
                                    "width": 100, "height": 140, "bytes": 1})


def test_best_condition_photo_wins(repo):
    """Showing a Damaged scan when a Near Mint copy exists misrepresents the
    collection."""
    hp = repo.upsert_collection_item({"card_id": "base1-12", "variant": "holo",
                                      "condition": "HP"})
    nm = repo.upsert_collection_item({"card_id": "base1-12", "variant": "normal",
                                      "condition": "M/NM"})
    _photo(repo, hp["id"], "bad.jpg")
    _photo(repo, nm["id"], "good.jpg")

    best = repo.best_photos_for_cards(["base1-12"])["base1-12"]
    assert best["filename"] == "collection/good.jpg"
    assert best["condition"] == "NM"


def test_primary_flag_breaks_ties_within_a_condition(repo):
    item = repo.upsert_collection_item({"card_id": "base1-12", "condition": "M/NM"})
    _photo(repo, item["id"], "first.jpg")
    second = _photo(repo, item["id"], "second.jpg")
    repo.set_primary_photo(second["id"])

    best = repo.best_photos_for_cards(["base1-12"])["base1-12"]
    assert best["filename"] == "collection/second.jpg"


def test_cards_without_photos_are_absent(repo):
    """Absence lets the caller fall through to catalog art, then the placeholder."""
    repo.upsert_collection_item({"card_id": "base1-4"})
    assert repo.best_photos_for_cards(["base1-4", "base1-12"]) == {}


def test_lookup_is_one_query_for_the_whole_page(repo):
    """A per-card lookup would be one query per grid tile — 240 on a full page."""
    for cid in ("base1-12", "base1-4"):
        item = repo.upsert_collection_item({"card_id": cid})
        _photo(repo, item["id"], f"{cid}.jpg")

    calls = []
    real = repo._all
    repo._all = lambda sql, params=(): (calls.append(sql), real(sql, params))[1]
    try:
        got = repo.best_photos_for_cards(["base1-12", "base1-4"])
    finally:
        repo._all = real

    assert set(got) == {"base1-12", "base1-4"}
    assert len(calls) == 1, f"expected 1 query, got {len(calls)}"


def test_duplicate_card_ids_are_deduped(repo):
    """The grid sends one id per row, so a card owned in three variants would
    otherwise appear three times in the IN clause."""
    item = repo.upsert_collection_item({"card_id": "base1-12"})
    _photo(repo, item["id"], "a.jpg")
    got = repo.best_photos_for_cards(["base1-12", "base1-12", "base1-12"])
    assert set(got) == {"base1-12"}


def test_empty_input_is_handled(repo):
    assert repo.best_photos_for_cards([]) == {}
