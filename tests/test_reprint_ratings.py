"""One card, one Hall of Fame rank, however many times it was printed (#76).

The rank moved off the collection row and onto the card once already — ranking
the holo and the non-holo separately was two answers to a question with one.
It stopped one step short: the Base Set Blastoise was a 3 and the Celebrations
Blastoise a 4. Same artwork, same power level, same card.

A rank now covers every printing of the card, an import cannot bring in an
unranked reprint of a ranked card, and a split that somehow appears anyway is
reported on the maintenance page instead of sitting there.
"""
import pytest

from tombot.config import Config
from tombot.services.health import check_reprint_ratings
from tombot.services.repository import PokemonRepo
from tombot.services.setbuilder import SetBuilder

SETS = [("bs", "Base", "1999/01/09"),
        ("b2", "Base Set 2", "2000/02/24"),
        ("cel", "Celebrations", "2021/10/08")]

# Three printings of Blastoise by the same illustrator, plus one card that only
# shares the name — the trap a name-only match would fall into.
CARDS = [
    ("bs-2", "bs", "Blastoise", "2", "Ken Sugimori"),
    ("b2-2", "b2", "Blastoise", "2", "Ken Sugimori"),
    ("cel-2", "cel", "Blastoise", "2", "Ken Sugimori"),
    ("bs-4", "bs", "Charizard", "4", "Mitsuhiro Arita"),
    ("b2-4", "b2", "Charizard", "4", "Another Artist"),
]


def _build(path):
    r = PokemonRepo(path)
    r.init_db()
    for sid, name, rd in SETS:
        r.upsert_official_set({"id": sid, "name": name, "series": "",
                               "printed_total": 2, "total": 2, "release_date": rd,
                               "ptcgo_code": sid.upper(), "logo_url": None,
                               "symbol_url": None})
    r.upsert_cards([{"id": i, "official_set_id": s, "name": n, "number": num,
                     "rarity": "Rare Holo", "artist": a}
                    for i, s, n, num, a in CARDS])
    return r


@pytest.fixture()
def repo(tmp_path):
    return _build(tmp_path / "r.db")


def _ranks(repo, ids):
    return {i: repo.get_card_rating(i) for i in ids}


# ------------------------------------------------------------ ranking ------
def test_ranking_one_printing_ranks_them_all(repo):
    """The complaint itself: rank the Base Set one, and Celebrations agrees."""
    repo.set_card_rating("bs-2", 4)
    assert _ranks(repo, ["bs-2", "b2-2", "cel-2"]) == {"bs-2": 4, "b2-2": 4, "cel-2": 4}


def test_ranking_from_any_printing_is_the_same_act(repo):
    """It is one card, so it does not matter which copy of it you opened."""
    repo.set_card_rating("cel-2", 7)
    assert _ranks(repo, ["bs-2", "b2-2", "cel-2"]) == {"bs-2": 7, "b2-2": 7, "cel-2": 7}


def test_clearing_a_rank_clears_every_printing(repo):
    """Otherwise unranking leaves the card ranked from another set's page."""
    repo.set_card_rating("bs-2", 5)
    repo.set_card_rating("b2-2", 0)
    assert _ranks(repo, ["bs-2", "b2-2", "cel-2"]) == {"bs-2": 0, "b2-2": 0, "cel-2": 0}


def test_a_shared_name_is_not_a_reprint(repo):
    """A reprint reuses the artwork. Two Charizards by different illustrators
    are two cards, and ranking one must not rank the other."""
    repo.set_card_rating("bs-4", 8)
    assert repo.get_card_rating("b2-4") == 0


def test_ranking_still_works_for_a_card_outside_the_catalogue(repo):
    """No reprints can be found for an unknown card, so it ranks alone rather
    than the write quietly matching nothing."""
    repo.set_card_rating("ghost-1", 6)
    assert repo.get_card_rating("ghost-1") == 0, "no card, no row — and no crash"


# --------------------------------------------------- resolving a split -----
def test_an_existing_split_resolves_to_the_most_recent_rank(tmp_path):
    """Tom's database has Blastoise at 3 in Base and 4 in Celebrations. The last
    rank he set is the one he meant; the older one predates him seeing the
    other printing."""
    repo = _build(tmp_path / "r.db")
    with repo.tx() as c:
        c.execute("INSERT INTO card_ratings(card_id, rating, updated_at) "
                  "VALUES ('bs-2', 3, '2026-01-01 10:00:00')")
        c.execute("INSERT INTO card_ratings(card_id, rating, updated_at) "
                  "VALUES ('cel-2', 4, '2026-02-01 10:00:00')")

    repo.unify_reprint_ratings()
    assert _ranks(repo, ["bs-2", "b2-2", "cel-2"]) == {"bs-2": 4, "b2-2": 4, "cel-2": 4}


def test_the_split_resolves_on_startup(tmp_path):
    """init_db runs it, so the database heals without anyone being told to."""
    repo = _build(tmp_path / "r.db")
    with repo.tx() as c:
        c.execute("INSERT INTO card_ratings(card_id, rating, updated_at) "
                  "VALUES ('bs-2', 3, '2026-01-01 10:00:00')")
    repo.init_db()
    assert repo.get_card_rating("cel-2") == 3


def test_the_pass_leaves_a_healthy_database_alone(repo):
    """Idempotent, and it must not touch the timestamps that decide the winner
    — rewriting them every start would let an old rank win a later split."""
    repo.set_card_rating("bs-2", 5)
    before = repo._all("SELECT card_id, rating, updated_at FROM card_ratings "
                       "ORDER BY card_id")
    assert repo.unify_reprint_ratings() == {"cards_ranked": 0, "groups": 0}
    after = repo._all("SELECT card_id, rating, updated_at FROM card_ratings "
                      "ORDER BY card_id")
    assert before == after


# ------------------------------------------------------------- imports -----
def test_a_set_imported_later_inherits_the_rank(repo):
    """Ranking Blastoise and then importing a set with another Blastoise used to
    reopen the split — the new printing arrived unranked, and it was invisible
    to the Hall of Fame filter."""
    repo.set_card_rating("bs-2", 6)
    repo.upsert_official_set({"id": "lc", "name": "Legendary Collection",
                              "series": "", "printed_total": 1, "total": 1,
                              "release_date": "2002/05/24", "ptcgo_code": "LC",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "lc-2", "official_set_id": "lc", "name": "Blastoise",
                        "number": "2", "rarity": "Rare Holo",
                        "artist": "Ken Sugimori"}])
    assert repo.get_card_rating("lc-2") == 6


def test_an_import_does_not_invent_a_rank(repo):
    """Nothing is ranked, so nothing gains a rank."""
    repo.upsert_cards([{"id": "cel-4", "official_set_id": "cel", "name": "Charizard",
                        "number": "4", "artist": "Mitsuhiro Arita"}])
    assert repo.get_card_rating("cel-4") == 0


# ------------------------------------------------------------- the check ---
def test_the_maintenance_page_reports_a_split(repo):
    """Belt and braces: if a rank is ever written past set_card_rating, the
    mismatch is a line on the page rather than a card in two places at once."""
    assert check_reprint_ratings(repo) == []
    with repo.tx() as c:
        c.execute("INSERT INTO card_ratings(card_id, rating) VALUES ('bs-2', 3)")
        c.execute("INSERT INTO card_ratings(card_id, rating) VALUES ('cel-2', 4)")
    found = check_reprint_ratings(repo)
    assert len(found) == 1 and "Blastoise" in found[0]["detail"][0]


# -------------------------------------------- the reprints-only toggle -----
@pytest.fixture()
def goal(repo):
    """One collecting goal per set, so the All view has every printing in it."""
    for sid, name, _ in SETS:
        repo.upsert_collection_set({"id": sid, "name": name,
                                    "rules_json": '{"include_sets": ["%s"]}' % sid})
        SetBuilder(repo).build(sid)
    return repo


def test_all_mode_lists_every_printing_by_default(goal):
    rows, total = goal.list_slots_with_ownership(page_size=100)
    assert total == 5
    assert sorted(r["card_id"] for r in rows
                  if r["name"] == "Blastoise") == ["b2-2", "bs-2", "cel-2"]


def test_unique_reprints_keeps_the_earliest_printing(goal):
    """Blastoise once, as the Base Set card — the original, not the reprint."""
    rows, total = goal.list_slots_with_ownership(unique_reprints=True, page_size=100)
    blastoise = [r for r in rows if r["name"] == "Blastoise"]
    assert len(blastoise) == 1 and blastoise[0]["card_id"] == "bs-2"
    assert total == 3, "Blastoise, and the two Charizards that are not reprints"


def test_unique_reprints_keeps_cards_that_only_share_a_name(goal):
    """Different illustrator, different card — collapsing them would hide one."""
    rows, _ = goal.list_slots_with_ownership(unique_reprints=True, page_size=100)
    assert sorted(r["card_id"] for r in rows
                  if r["name"] == "Charizard") == ["b2-4", "bs-4"]


def test_unique_reprints_picks_within_the_filter(goal):
    """"La primera que exista para ese filtro": narrowed to Celebrations, the
    Celebrations printing is the only candidate and so it is the one shown."""
    rows, total = goal.list_slots_with_ownership(set_id="cel", unique_reprints=True,
                                                 page_size=100)
    assert total == 1 and rows[0]["card_id"] == "cel-2"


def test_unique_reprints_pages_by_card(goal):
    """The count under the toolbar has to be the number of tiles, or the last
    page comes back empty."""
    rows, total = goal.list_slots_with_ownership(unique_reprints=True,
                                                 page=1, page_size=2)
    assert total == 3 and len(rows) == 2
    page2, _ = goal.list_slots_with_ownership(unique_reprints=True,
                                              page=2, page_size=2)
    assert len(page2) == 1


def test_unique_reprints_keeps_the_ownership_of_the_printing_it_shows(goal):
    """It shows the Base Set Blastoise, and that is the one whose ownership it
    reports. Owning the Celebrations reprint does not make the Base Set card
    yours, and a tile claiming otherwise is the lie this app keeps chasing."""
    goal.upsert_collection_item({"card_id": "cel-2"})
    rows, _ = goal.list_slots_with_ownership(unique_reprints=True, page_size=100)
    blastoise = next(r for r in rows if r["name"] == "Blastoise")
    assert blastoise["card_id"] == "bs-2" and blastoise["owned"] is False


def test_the_endpoint_takes_the_toggle(goal, tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "r.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "catalog"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "collection"),
                        ("THUMB_DIR", tmp_path / "m" / "thumbs")):
        monkeypatch.setattr(Config, attr, value)
    from tombot import create_app
    app = create_app(Config)
    app.config["TESTING"] = True
    client = app.test_client()

    every = client.get("/api/collection?show_all=1").get_json()
    once = client.get("/api/collection?show_all=1&unique_reprints=1").get_json()
    assert every["total"] == 5 and once["total"] == 3


def test_a_card_whose_reprint_you_own_says_so(goal):
    """It shows the Base Set Blastoise, which you have not got — but you have
    the Celebrations one. Claiming the tile is owned would be a lie; drawing it
    as plain missing hides a card you actually have."""
    goal.upsert_collection_item({"card_id": "cel-2"})
    rows, _ = goal.list_slots_with_ownership(unique_reprints=True, page_size=100)
    blastoise = next(r for r in rows if r["name"] == "Blastoise")
    assert blastoise["owned"] is False and blastoise["reprint_owned"] is True


def test_a_card_you_actually_own_is_not_flagged_as_a_reprint(goal):
    """The two markings are exclusive, or an owned card carries both."""
    goal.upsert_collection_item({"card_id": "bs-2"})
    rows, _ = goal.list_slots_with_ownership(unique_reprints=True, page_size=100)
    blastoise = next(r for r in rows if r["name"] == "Blastoise")
    assert blastoise["owned"] is True and blastoise["reprint_owned"] is False


def test_the_flag_is_off_when_the_toggle_is(goal):
    """It answers a question only the reprints view asks, so it costs nothing
    on the ordinary listing."""
    goal.upsert_collection_item({"card_id": "cel-2"})
    rows, _ = goal.list_slots_with_ownership(page_size=100)
    assert all(r["reprint_owned"] is False for r in rows)
