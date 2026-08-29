"""Finding a set to import, after syncing tcggo's catalogue locally.

tcggo names disagree with what people type — it calls Base Set "Base" — and its
own search only matches its own names, so common queries miss real sets. The fix
is to cache the whole catalogue and search it locally, bidirectionally: a set
matches when its name contains the query OR the query contains its name.
"""
import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "e.db")
    r.init_db(DEFAULT_MODIFIERS)
    # what the tcggo catalogue actually stores for these sets
    r.remember_episodes([
        {"id": 171, "code": "BS", "name": "Base", "released_at": "1999-01-09"},
        {"id": 167, "code": "B2", "name": "Base Set 2", "released_at": "2000-02-24"},
        {"id": 157, "code": "EX", "name": "Expedition Base Set", "released_at": "2002-09-15"},
        {"id": 170, "code": "JU", "name": "Jungle", "released_at": "1999-06-16"},
    ])
    return r


def _names(rows):
    return {r["name"] for r in rows}


def test_common_name_finds_the_set_tcggo_calls_something_shorter(repo):
    # "Base Set" must find "Base" — the query is longer than the stored name.
    assert "Base" in _names(repo.search_known_episodes("Base Set"))


def test_the_short_query_still_finds_everything(repo):
    got = _names(repo.search_known_episodes("Base"))
    assert {"Base", "Base Set 2", "Expedition Base Set"} <= got


def test_code_search_works(repo):
    assert _names(repo.search_known_episodes("BS")) == {"Base"}


def test_an_unrelated_query_matches_nothing(repo):
    assert repo.search_known_episodes("Charizard") == []


def test_no_query_lists_the_whole_catalogue_newest_first(repo):
    rows = repo.search_known_episodes(None)
    assert [r["name"] for r in rows][0] == "Expedition Base Set"   # 2002, newest
    assert len(rows) == 4


def test_remember_episodes_is_idempotent(repo):
    # Re-syncing must not duplicate rows (upsert on episode_id).
    repo.remember_episodes([{"id": 171, "code": "BS", "name": "Base",
                             "released_at": "1999-01-09"}])
    assert len([r for r in repo.search_known_episodes(None) if r["episode_id"] == 171]) == 1
