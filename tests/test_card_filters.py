"""Type, edition and quantity filters in the Cartas view."""
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
                           "printed_total": 3, "total": 3,
                           "release_date": "1999/01/09", "ptcgo_code": None,
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard",
         "number": "4", "types": ["Fire"]},
        {"id": "base1-2", "official_set_id": "base1", "name": "Blastoise",
         "number": "2", "types": ["Water"]},
        {"id": "base1-9", "official_set_id": "base1", "name": "Magneton",
         "number": "9", "types": ["Lightning", "Metal"]},
    ])
    yield r
    os.unlink(path)


def test_card_types_are_discovered_from_the_catalog(repo):
    assert repo.card_types() == ["Fire", "Lightning", "Metal", "Water"]


def test_type_filter_matches_one_of_several_types(repo):
    """types_json is a list; a card can be both Lightning and Metal."""
    for cid in ("base1-4", "base1-2", "base1-9"):
        repo.upsert_collection_item({"card_id": cid})

    fire, _ = repo.list_collection(card_type="Fire")
    assert [i["card_id"] for i in fire] == ["base1-4"]
    metal, _ = repo.list_collection(card_type="Metal")
    assert [i["card_id"] for i in metal] == ["base1-9"]


def test_type_filter_does_not_match_substrings(repo):
    """Matching on the quoted value stops 'Fire' matching a hypothetical
    'Firestorm' — the reason the LIKE pattern includes the quotes."""
    repo.upsert_cards([{"id": "base1-99", "official_set_id": "base1",
                        "name": "Test", "number": "99", "types": ["Firestorm"]}])
    repo.upsert_collection_item({"card_id": "base1-99"})
    repo.upsert_collection_item({"card_id": "base1-4"})
    fire, _ = repo.list_collection(card_type="Fire")
    assert [i["card_id"] for i in fire] == ["base1-4"]


def test_edition_filter_separates_first_edition_from_unlimited(repo):
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "first_edition"})
    repo.upsert_collection_item({"card_id": "base1-2", "variant": "shadowless"})
    repo.upsert_collection_item({"card_id": "base1-9", "variant": "holo"})

    first, _ = repo.list_collection(edition="first_edition")
    assert [i["card_id"] for i in first] == ["base1-4"]

    # Unlimited means an ordinary copy: not 1st Edition and not Shadowless.
    unlimited, _ = repo.list_collection(edition="unlimited")
    assert [i["card_id"] for i in unlimited] == ["base1-9"]


def test_quantity_filter_counts_the_card_not_the_row(repo):
    """'2 or more' asks about the card. Three copies split across a holo row and
    a normal row is three copies, so the card must not be excluded just because
    each individual row is small."""
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo", "quantity": 1})
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "normal", "quantity": 2})
    repo.upsert_collection_item({"card_id": "base1-2", "quantity": 1})

    three_plus, _ = repo.list_collection(min_quantity=3)
    assert {i["card_id"] for i in three_plus} == {"base1-4"}, "3 copies across two rows"

    one_plus, _ = repo.list_collection(min_quantity=1)
    assert {i["card_id"] for i in one_plus} == {"base1-4", "base1-2"}

    four_plus, _ = repo.list_collection(min_quantity=4)
    assert four_plus == []


def test_filters_compose(repo):
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "first_edition",
                                 "quantity": 1})
    repo.upsert_collection_item({"card_id": "base1-2", "variant": "first_edition",
                                 "quantity": 5})
    got, _ = repo.list_collection(edition="first_edition", min_quantity=1, card_type="Fire")
    assert [i["card_id"] for i in got] == ["base1-4"]
