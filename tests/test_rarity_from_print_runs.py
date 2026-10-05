"""A card's rarity comes from its first print run, not the one with stock (#105).

tcggo files each print run of a card as its own product, and the runs disagree
on rarity: Team Rocket's "Here Comes Team Rocket!" (TR 15) is "Rare Holo" as
1st Edition and "SECRET RARE" as Unlimited; Dark Muk (TR 41) is "Uncommon" and
"rare". The import used to take the rarity from the run with more sellers, so
TR 15 became a secret rare on the day Unlimited had three more offers than
1st Edition, and filed itself beside Dark Raichu (83/82) in the filter.
"""
import pytest

from tombot.services.repository import PokemonRepo
from tombot.services.tcggo_catalog import (TcggoCatalog, card_rarity,
                                           rederive_stored_rarities)

TEAM_ROCKET = {"id": 7, "code": "TR", "name": "Team Rocket",
               "released_at": "2000-04-24", "cards_printed_total": 82,
               "cards_total": 83}


def _prod(pid, card_id, code, number, name, version, rarity, available):
    return {"cardmarket_id": pid, "episode_id": 7, "card_id": card_id,
            "code": code, "number": number, "name": name, "version": version,
            "rarity": rarity, "currency": "EUR", "price": 10.0, "price_low": 5.0,
            "price_avg30": None, "price_avg7": None, "available": available,
            "image": None, "market_url": f"https://x/{pid}", "artist": "Ken Sugimori"}


# What tcggo actually returns for these, availability as seen on 2026-10-05.
HERE_COMES = [_prod(1, "tr-15", "TR 15", "15", "Here Comes Team Rocket!",
                    "1st Edition", "Rare Holo", 236),
              _prod(2, "tr-15", "TR 15", "15", "Here Comes Team Rocket!",
                    "Unlimited", "SECRET RARE", 239)]
DARK_MUK = [_prod(3, "tr-41", "TR 41", "41", "Dark Muk",
                  "1st Edition", "Uncommon", 636),
            _prod(4, "tr-41", "TR 41", "41", "Dark Muk",
                  "Unlimited", "rare", 586)]
DARK_RAICHU = [_prod(5, "tr-83", "TR 83", "83", "Dark Raichu",
                     "1st Edition", "Rare Secret", 278),
               _prod(6, "tr-83", "TR 83", "83", "Dark Raichu",
                     "Unlimited", "SECRET RARE", 277)]


def test_the_first_print_run_decides_the_rarity():
    assert card_rarity(HERE_COMES) == "Rare Holo"      # not the Unlimited's
    assert card_rarity(DARK_MUK) == "Uncommon"
    assert card_rarity(DARK_RAICHU) == "Rare Secret"   # runs agree; still right
    assert card_rarity(list(reversed(HERE_COMES))) == "Rare Holo", "order-free"


def test_a_run_without_a_rarity_yields_to_one_with():
    runs = [_prod(1, "x-1", "X 1", "1", "Foo", "1st Edition", "", 9),
            _prod(2, "x-1", "X 1", "1", "Foo", "Unlimited", "Common", 1)]
    assert card_rarity(runs) == "Common"
    assert card_rarity([]) is None


def test_a_modern_single_run_is_used_as_is():
    assert card_rarity([_prod(1, "evo-113", "EVO 113", "113", "Here Comes",
                              "", "Rare Secret", 268)]) == "Rare Secret"


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "r.db")
    r.init_db()
    return r


def test_import_does_not_let_todays_stock_pick_the_rarity(repo):
    repo.upsert_market_products(HERE_COMES + DARK_MUK + DARK_RAICHU)
    TcggoCatalog(repo).build_set(TEAM_ROCKET)
    got = {c["id"]: c["rarity"] for c in repo._all("SELECT id, rarity FROM cards")}
    assert got == {"tr-15": "Rare Holo", "tr-41": "Uncommon", "tr-83": "Rare Secret"}


def test_an_existing_database_is_re_decided_from_its_products(repo):
    """What Tom's database holds, fixed on the next start with no reimport."""
    repo.upsert_market_products(HERE_COMES + DARK_MUK + DARK_RAICHU)
    TcggoCatalog(repo).build_set(TEAM_ROCKET)
    with repo.tx() as c:
        c.execute("UPDATE cards SET rarity='Rare Secret' WHERE id='tr-15'")
    result = rederive_stored_rarities(repo)
    assert result["cards"] == 1 and result["detail"] == ["tr-15 → Rare Holo"]
    assert repo._one("SELECT rarity FROM cards WHERE id='tr-15'")["rarity"] == "Rare Holo"
    assert rederive_stored_rarities(repo)["cards"] == 0, "idempotent"
    # And init_db runs it, which is what a restart does.
    with repo.tx() as c:
        c.execute("UPDATE cards SET rarity='Rare Secret' WHERE id='tr-15'")
    repo.init_db()
    assert repo._one("SELECT rarity FROM cards WHERE id='tr-15'")["rarity"] == "Rare Holo"
