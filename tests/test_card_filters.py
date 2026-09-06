"""Type, edition and quantity filters in the Cartas view."""
import os
import tempfile

import pytest

from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = PokemonRepo(path)
    r.init_db()
    r.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                           "printed_total": 3, "total": 3,
                           "release_date": "1999/01/09", "ptcgo_code": None,
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard",
         "number": "4", "supertype": "Pokémon"},
        {"id": "base1-2", "official_set_id": "base1", "name": "Blastoise",
         "number": "2", "supertype": "Pokémon"},
        {"id": "base1-9", "official_set_id": "base1", "name": "Magneton",
         "number": "9", "supertype": "Pokémon"},
        {"id": "base1-88", "official_set_id": "base1", "name": "Professor Oak",
         "number": "88", "supertype": "Trainer"},
        {"id": "base1-98", "official_set_id": "base1", "name": "Fire Energy",
         "number": "98", "supertype": "Energy"},
    ])
    yield r
    os.unlink(path)


def test_card_supertypes_are_discovered_from_the_catalog(repo):
    """The "Tipo" filter is the supertype — the only card type tcggo carries."""
    assert repo.card_supertypes() == ["Energy", "Pokémon", "Trainer"]


def test_type_filter_matches_the_supertype(repo):
    for cid in ("base1-4", "base1-88", "base1-98"):
        repo.upsert_collection_item({"card_id": cid})

    trainers, _ = repo.list_collection(card_type="Trainer")
    assert [i["card_id"] for i in trainers] == ["base1-88"]
    energy, _ = repo.list_collection(card_type="Energy")
    assert [i["card_id"] for i in energy] == ["base1-98"]
    pokemon, _ = repo.list_collection(card_type="Pokémon")
    assert [i["card_id"] for i in pokemon] == ["base1-4"]


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
                                 "quantity": 1})                       # Pokémon
    repo.upsert_collection_item({"card_id": "base1-88", "variant": "first_edition",
                                 "quantity": 5})                       # Trainer
    got, _ = repo.list_collection(edition="first_edition", min_quantity=1,
                                  card_type="Pokémon")
    assert [i["card_id"] for i in got] == ["base1-4"]


# ------------------------------------------------------------- energy type
def _with_types(repo):
    """The colour is not something tcggo sends, so it arrives the way it does in
    production: filled onto already-imported cards."""
    repo.fill_card_fields({"types_json": [('["Fire"]', "base1-4"),
                                          ('["Water"]', "base1-2"),
                                          ('["Lightning","Metal"]', "base1-9")]})


def test_energy_types_are_discovered_from_the_catalog(repo):
    assert repo.card_energy_types() == []            # nothing filled yet
    _with_types(repo)
    assert repo.card_energy_types() == ["Fire", "Lightning", "Metal", "Water"]


def test_color_filter_is_independent_of_the_supertype(repo):
    """Supertype (Pokémon/Trainer/Energy) and colour (Fire/Water/…) are two
    axes: a Fire filter must not care that a Fire Energy is not a Pokémon, and a
    Pokémon filter must not care about colour. Both together narrow further."""
    _with_types(repo)
    repo.fill_card_fields({"types_json": [('["Fire"]', "base1-98")]})   # Fire Energy
    for cid in ("base1-4", "base1-2", "base1-9", "base1-88", "base1-98"):
        repo.upsert_collection_item({"card_id": cid})

    fire, _ = repo.list_collection(energy_type="Fire")
    assert {i["card_id"] for i in fire} == {"base1-4", "base1-98"}
    fire_pokemon, _ = repo.list_collection(energy_type="Fire", card_type="Pokémon")
    assert [i["card_id"] for i in fire_pokemon] == ["base1-4"]
    pokemon, _ = repo.list_collection(card_type="Pokémon")
    assert {i["card_id"] for i in pokemon} == {"base1-4", "base1-2", "base1-9"}


def test_color_filter_matches_either_type_of_a_dual_type_card(repo):
    _with_types(repo)
    repo.upsert_collection_item({"card_id": "base1-9"})
    for colour in ("Lightning", "Metal"):
        got, _ = repo.list_collection(energy_type=colour)
        assert [i["card_id"] for i in got] == ["base1-9"], colour
    none, _ = repo.list_collection(energy_type="Grass")
    assert none == []


def test_color_filter_applies_to_the_all_cards_view(repo):
    _with_types(repo)
    repo.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    repo.replace_rule_slots("mine", [
        {"position": i, "label": cid, "cards": [cid], "display_card_id": cid}
        for i, cid in enumerate(("base1-4", "base1-2", "base1-9"))])
    rows, total = repo.list_slots_with_ownership(energy_type="Water", page_size=100)
    assert total == 1 and rows[0]["card_id"] == "base1-2" and rows[0]["owned"] is False


def test_reimport_keeps_a_locally_filled_energy_type(repo):
    """tcggo never sends a type, so every import carries an empty list; a
    re-import (which refreshes prices) must not wipe the CSV-filled colour.
    A non-empty incoming list still wins, as any other imported field does."""
    _with_types(repo)
    repo.upsert_cards([{"id": "base1-4", "official_set_id": "base1",
                        "name": "Charizard", "number": "4", "supertype": "Pokémon"}])
    assert repo.get_card("base1-4")["types_json"] == '["Fire"]'
    repo.upsert_cards([{"id": "base1-4", "official_set_id": "base1",
                        "name": "Charizard", "number": "4", "types": ["Dragon"]}])
    assert repo.get_card("base1-4")["types_json"] == '["Dragon"]'
