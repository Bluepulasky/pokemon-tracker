"""Re-pricing a collection that was entered before per-print-run pricing.

Reported from a live install: an existing Hitmonchan kept its old price through
rebuilds while a newly added Ninetales priced correctly. Both causes are here.
"""
import os
import tempfile

import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo
from tombot.services.variant_map import resolve


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
        {"id": "base1-7", "official_set_id": "base1", "name": "Hitmonchan",
         "number": "7", "rarity": "Rare Holo"},
        {"id": "base1-12", "official_set_id": "base1", "name": "Ninetales",
         "number": "12", "rarity": "Rare Holo"},
    ])
    yield r
    os.unlink(path)


def _legacy_price(repo, card_id, variant, price):
    """A row as written before prices were resolved per print run: no variant_key."""
    with repo.tx() as c:
        c.execute("""INSERT INTO price_cache(card_id,variant,source,currency,price,updated_at)
                     VALUES (?,?,'cardmarket','EUR',?,datetime('now'))""",
                  (card_id, variant, price))


def test_a_fresh_but_pre_change_price_still_counts_as_stale(repo):
    """The reported asymmetry. Age alone said this row was fine, so an existing
    card kept its old price forever while a new one priced correctly."""
    repo.upsert_collection_item({"card_id": "base1-7", "variant": "normal"})
    _legacy_price(repo, "base1-7", "normal", 70.61)
    repo.upsert_collection_item({"card_id": "base1-12", "variant": "holo"})

    queued = {p["card_id"] for p in repo.stale_priced_pairs(25)}
    assert "base1-7" in queued, "a row with no variant_key must be re-priced"
    assert "base1-12" in queued, "a card with no row at all was already fine"


def test_a_current_price_is_left_alone(repo):
    repo.upsert_collection_item({"card_id": "base1-7", "variant": "holo"})
    repo.upsert_price("base1-7", "holo", "cardmarket", "EUR", 14.29,
                      None, None, None, None, variant_key="holo:unlimited")
    assert repo.stale_priced_pairs(25) == []


def test_manual_prices_are_never_queued(repo):
    repo.upsert_collection_item({"card_id": "base1-7", "variant": "holo"})
    _legacy_price(repo, "base1-7", "holo", 70.61)
    repo.set_manual_price("base1-7", "holo", 9.99)
    assert repo.stale_priced_pairs(25) == []

    repo.set_manual_price("base1-7", "holo", None)
    assert {p["card_id"] for p in repo.stale_priced_pairs(25)} == {"base1-7"}


def test_legacy_rows_are_countable(repo):
    repo.upsert_collection_item({"card_id": "base1-7", "variant": "holo"})
    _legacy_price(repo, "base1-7", "holo", 70.61)
    assert repo.count_legacy_prices() == 1


# ------------------------------------------------ the vocabulary mismatch
BASE1_7 = ["holo:unlimited", "holo:shadowless:1st-edition",
           "holo:shadowless", "holo:1999-2000-copyright"]


def test_a_plain_variant_falls_back_to_the_one_ordinary_printing():
    """Base Set Hitmonchan only ever existed as holo, but a collection can record
    it as 'normal' — the app offers that word for every card. Refusing to price it
    would lose a price over a vocabulary mismatch rather than a real ambiguity."""
    assert resolve("normal", BASE1_7) == "holo:unlimited"
    assert resolve("holo", BASE1_7) == "holo:unlimited"


def test_special_runs_never_fall_back():
    """Choosing between print runs is the mistake this whole change exists to
    prevent, so shadowless, 1st edition and reverse either match or return None."""
    only_plain = ["holo:unlimited"]
    assert resolve("shadowless", only_plain) is None
    assert resolve("first_edition", only_plain) is None
    assert resolve("reverse", only_plain) is None


def test_no_fallback_when_several_ordinary_printings_exist():
    """With more than one plain printing there is a genuine choice, so it must
    not be made silently."""
    several = ["normal", "reverse:set-logo"]
    assert resolve("holo", several) is None


# ------------------------------------------------ build identification
def test_the_running_build_is_reported(tmp_path, monkeypatch):
    """Diagnosing a report against a deployed instance means knowing which commit
    it serves. Without it, "it still shows the old price" is ambiguous between a
    bug and an image that was never rebuilt — which came up in practice."""
    from tombot.config import Config
    from tombot.version import get_version

    monkeypatch.setenv("APP_VERSION", "deadbee")
    assert get_version() == "deadbee", "a baked-in version wins"

    monkeypatch.setattr(Config, "DB_PATH", tmp_path / "v.db")
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(Config, "CATALOG_IMG_DIR", tmp_path / "media" / "catalog")
    monkeypatch.setattr(Config, "COLLECTION_IMG_DIR", tmp_path / "media" / "collection")
    monkeypatch.setattr(Config, "THUMB_DIR", tmp_path / "media" / "thumbs")
    PokemonRepo(Config.DB_PATH).init_db(DEFAULT_MODIFIERS)

    from tombot import create_app
    client = create_app(Config).test_client()
    assert client.get("/api/healthz").get_json()["version"] == "deadbee"
    assert client.get("/api/meta").get_json()["version"] == "deadbee"


def test_an_unstamped_build_says_so_rather_than_guessing(monkeypatch):
    """`.dockerignore` excludes .git, so an image built without the build arg has
    no way to know. Reporting "unknown" is honest; inventing a version is not."""
    import tombot.version as version

    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setattr(version, "_from_git", lambda: None)
    monkeypatch.setattr(version, "_git_cache", ...)
    assert version.get_version() == "unknown"
