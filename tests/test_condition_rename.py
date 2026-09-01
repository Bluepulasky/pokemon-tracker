"""Carrying the condition rename through data as well as code (issue #26).

A grade with no home in the current vocabulary does not fail — a card stored on
it just drops out of the condition filter and sorts to the bottom in silence —
so every gap here is invisible unless something checks for it.
"""
from tombot.config import CONDITIONS, RETIRED_CONDITIONS
from tombot.services.repository import PokemonRepo


def _repo(tmp_path, name="c.db"):
    r = PokemonRepo(tmp_path / name)
    r.init_db()
    r.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                           "printed_total": 2, "total": 2,
                           "release_date": "1999/01/09", "ptcgo_code": "BS",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([{"id": "base1-4", "official_set_id": "base1",
                     "name": "Charizard", "number": "4"},
                    {"id": "base1-7", "official_set_id": "base1",
                     "name": "Hitmonchan", "number": "7"}])
    return r


def test_every_retired_grade_maps_to_a_live_one():
    """A typo here would send cards to a grade the app no longer offers."""
    assert set(RETIRED_CONDITIONS.values()) <= set(CONDITIONS)


def test_a_row_saved_without_a_condition_gets_a_live_grade(tmp_path):
    """The default used to be 'NM', which is no longer a live grade."""
    repo = _repo(tmp_path)
    item = repo.upsert_collection_item({"card_id": "base1-7", "variant": "holo"})
    assert item["condition"] in CONDITIONS
