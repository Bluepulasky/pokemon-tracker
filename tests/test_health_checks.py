"""The checks exist because five bugs shared one shape and none failed a test.

Each test here breaks the data the way it was really broken, and asserts the
check notices. A silent fallback is the failure mode, so "notices" means an
explicit finding rather than a plausible number.
"""
import pytest

from tombot.config import CONDITIONS
from tombot.services.health import run_checks
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "h.db")
    r.init_db()
    r.upsert_official_set({"id": "bs", "name": "Base Set", "series": "Base",
                           "printed_total": 2, "total": 2,
                           "release_date": "1999/01/09", "ptcgo_code": "BS",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([{"id": "bs-4", "official_set_id": "bs", "name": "Charizard",
                     "number": "4", "rarity": "Rare Holo"},
                    {"id": "bs-7", "official_set_id": "bs", "name": "Hitmonchan",
                     "number": "7", "rarity": "Rare Holo"}])
    return r


def _levels(result, check):
    return [f for f in result["findings"] if f["check"] == check]


def test_clean_data_reports_nothing(repo):
    result = run_checks(repo, CONDITIONS)
    assert result["ok"]
    assert result["errors"] == 0


def test_a_renamed_grade_left_on_a_card_is_reported(repo):
    """A card stored on a grade the app no longer offers, reported not silent."""
    with repo.tx() as c:
        c.execute("""INSERT INTO collection_items(card_id, variant, condition,
                        language, quantity) VALUES('bs-4','holo','LP','en',1)""")

    result = run_checks(repo, CONDITIONS)

    found = _levels(result, "conditions")
    assert found and found[0]["level"] == "error"
    assert "LP" in found[0]["detail"]
    assert not result["ok"]


def test_two_spellings_of_one_rarity_are_reported(repo):
    """"Rare Holo" and "Holo Rare" built a 51-card set called 48."""
    repo.upsert_cards([{"id": "bs-9", "official_set_id": "bs", "name": "Magneton",
                        "number": "9", "rarity": "Holo Rare"}])

    result = run_checks(repo, CONDITIONS)

    found = _levels(result, "rarities")
    assert found and found[0]["level"] == "error"
    assert any("Holo Rare" in d and "Rare Holo" in d for d in found[0]["detail"])


def test_a_set_without_a_release_date_is_reported(repo):
    """Without it the era is guessed from the set id, which offered reverse
    holos on Base Set."""
    with repo.tx() as c:
        c.execute("UPDATE official_sets SET release_date='' WHERE id='bs'")

    found = _levels(run_checks(repo, CONDITIONS), "set_dates")
    assert found
    assert "reverse holos" in found[0]["message"]


def test_a_number_carrying_its_set_code_is_reported(repo):
    """"BS 4" as a number is how one card became two."""
    repo.upsert_cards([{"id": "bs-bs-4", "official_set_id": "bs",
                        "name": "Charizard", "number": "BS 4",
                        "rarity": "Rare Holo"}])

    found = _levels(run_checks(repo, CONDITIONS), "card_numbers")
    assert found and found[0]["level"] == "error"
    assert any("BS 4" in d for d in found[0]["detail"])


def test_cards_with_no_rarity_are_reported(repo):
    """A rule about rarity skips them without saying so."""
    repo.upsert_cards([{"id": "bs-99", "official_set_id": "bs", "name": "Ghost",
                        "number": "99", "rarity": None}])

    found = [f for f in _levels(run_checks(repo, CONDITIONS), "rarities")
             if "rareza" in f["message"]]
    assert found
