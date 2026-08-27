"""Carrying the condition rename through data as well as code (issue #26).

A grade with no multiplier row does not fail — it falls back to 1.00 — so
every gap here is silent and flatters the collection's value.
"""
import pytest

from tombot.config import CONDITIONS, DEFAULT_MODIFIERS, RETIRED_CONDITIONS, Config
from tombot.services.repository import PokemonRepo


def _repo(tmp_path, name="c.db"):
    r = PokemonRepo(tmp_path / name)
    r.init_db(DEFAULT_MODIFIERS)
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
    """A typo here would send cards to a grade with no multiplier."""
    assert set(RETIRED_CONDITIONS.values()) <= set(CONDITIONS)


def test_cards_on_old_grades_are_carried_over(tmp_path):
    repo = _repo(tmp_path)
    with repo.tx() as c:
        c.execute("""INSERT INTO collection_items(card_id, variant, condition, language,
                                                  quantity) VALUES('base1-4','holo','LP','en',2)""")
    repo.init_db(DEFAULT_MODIFIERS)          # a restart runs the migrations

    rows = repo._all("SELECT condition, quantity FROM collection_items")
    assert rows == [{"condition": "EX", "quantity": 2}]


def test_a_card_held_under_both_names_merges_instead_of_colliding(tmp_path):
    """(card, variant, condition, language) is unique; one row must not vanish."""
    repo = _repo(tmp_path)
    with repo.tx() as c:
        c.execute("""INSERT INTO collection_items(card_id, variant, condition, language,
                                                  quantity) VALUES('base1-4','holo','NM','en',2)""")
        c.execute("""INSERT INTO collection_items(card_id, variant, condition, language,
                                                  quantity) VALUES('base1-4','holo','M/NM','en',3)""")
    repo.init_db(DEFAULT_MODIFIERS)

    rows = repo._all("SELECT condition, quantity FROM collection_items")
    assert rows == [{"condition": "M/NM", "quantity": 5}], "quantities add up"


def test_multipliers_for_retired_grades_are_dropped(tmp_path):
    """Tom's table listed eleven rows for five grades, old and new together."""
    repo = _repo(tmp_path)
    for stale in ("NM", "LP", "MP", "HP", "DMG", "N/NM"):
        repo.set_modifier("condition", stale, 0.5)
    repo.init_db(DEFAULT_MODIFIERS)

    keys = {m["key"] for m in repo._all(
        "SELECT key FROM price_modifiers WHERE kind='condition'")}
    assert keys == set(CONDITIONS)


def test_edited_multipliers_for_live_grades_survive(tmp_path):
    """The cleanup must not undo what someone deliberately changed."""
    repo = _repo(tmp_path)
    repo.set_modifier("condition", "EX", 0.91)
    repo.init_db(DEFAULT_MODIFIERS)

    mods = repo.get_modifiers()
    assert mods["condition"]["EX"] == pytest.approx(0.91)


def test_a_row_saved_without_a_condition_gets_a_live_grade(tmp_path):
    """The default used to be 'NM', which now has no multiplier at all."""
    repo = _repo(tmp_path)
    item = repo.upsert_collection_item({"card_id": "base1-7", "variant": "holo"})
    assert item["condition"] in CONDITIONS


def test_the_api_refuses_an_unknown_condition_multiplier(tmp_path, monkeypatch):
    """This is how a stray key got into the table in the first place."""
    for attr, value in (("DB_PATH", tmp_path / "api.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    PokemonRepo(Config.DB_PATH).init_db(DEFAULT_MODIFIERS)
    from tombot import create_app
    client = create_app(Config).test_client()

    # A retired grade is the realistic typo: it reads as valid and is not.
    bad = client.put("/api/prices/modifiers/condition/NM", json={"multiplier": 1.0})
    assert bad.status_code == 400
    assert "desconocida" in bad.get_json()["error"]["message"]

    # A key with a slash cannot reach the route at all — Werkzeug refuses %2F
    # in a path segment — so "N/NM" was never created through the API. The
    # cleanup migration is what removes it.
    assert client.put("/api/prices/modifiers/condition/N%2FNM",
                      json={"multiplier": 1.0}).status_code == 404

    good = client.put("/api/prices/modifiers/condition/EX", json={"multiplier": 0.9})
    assert good.status_code == 200
