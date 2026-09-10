"""One tile per card in the Cartas view (issue #78).

Two copies of a card are two rows in `collection_items` — a Dragonair held M/NM
in Base Set and EX in Base Set 2, a Hitmonchan held EX and GD. The grid drew one
tile per row, so the card was counted twice, its value was split across two
prices, and the two tiles disagreed: one modal listed both copies, the other
listed one. A card is now one tile, standing on the best-conditioned copy,
badged with every copy and priced as their sum.
"""
import pytest

from tombot.config import Config
from tombot.services.pricing import PricingService
from tombot.services.repository import PokemonRepo
from tombot.services.setbuilder import SetBuilder


def _product(pid, card_id, number, price):
    return {"cardmarket_id": pid, "episode_id": 1, "card_id": card_id,
            "code": f"X {number}", "number": number, "name": "x",
            "version": "Unlimited", "rarity": "Rare", "currency": "EUR",
            "price": price, "price_low": None, "price_avg30": None,
            "price_avg7": None, "available": 1, "image": None,
            "market_url": f"https://x/{pid}"}


def _own(repo, card_id, **item):
    """Own a copy pinned to its own printing, which is what makes it priceable.
    English so the language factor is 1.00 and the sums read as the raw prices.
    """
    products = repo.market_products_for_card(card_id)
    return repo.upsert_collection_item({
        "card_id": card_id, "language": "en",
        "market_product_id": products[0]["id"] if products else None, **item})


def _build(tmp_path):
    r = PokemonRepo(tmp_path / "r.db")
    r.init_db()
    for sid, name, rd in [("bs", "Base", "1999/01/09"),
                          ("b2", "Base Set 2", "2000/02/24")]:
        r.upsert_official_set({"id": sid, "name": name, "series": "",
                               "printed_total": 2, "total": 2, "release_date": rd,
                               "ptcgo_code": sid.upper(), "logo_url": None,
                               "symbol_url": None})
    r.upsert_cards([
        # The same card twice over: same name, same illustrator, two printings.
        {"id": "bs-18", "official_set_id": "bs", "name": "Dragonair",
         "number": "18", "rarity": "Rare", "artist": "Mitsuhiro Arita"},
        {"id": "b2-22", "official_set_id": "b2", "name": "Dragonair",
         "number": "22", "rarity": "Rare", "artist": "Mitsuhiro Arita"},
        # A name it shares with nothing, to prove grouping is not by name alone.
        {"id": "bs-7", "official_set_id": "bs", "name": "Hitmonchan",
         "number": "7", "rarity": "Rare Holo", "artist": "Ken Sugimori"},
        # Same name, different illustrator: a different card, not a reprint.
        {"id": "b2-8", "official_set_id": "b2", "name": "Hitmonchan",
         "number": "8", "rarity": "Rare Holo", "artist": "Keiji Kinebuchi"},
    ])
    r.upsert_market_products([
        _product(1, "bs-18", "18", 14.31),
        _product(2, "b2-22", "22", 7.64),
        _product(3, "bs-7", "7", 12.57),
    ])
    return r


@pytest.fixture()
def repo(tmp_path):
    return _build(tmp_path)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "r.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "catalog"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "collection"),
                        ("THUMB_DIR", tmp_path / "m" / "thumbs")):
        monkeypatch.setattr(Config, attr, value)
    repo = _build(tmp_path)

    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.repo = repo
    return a


def _cards(rows):
    return [r["card_id"] for r in rows]


# ----------------------------------------------------- the grid collapses ---
def test_a_reprint_and_its_original_are_one_tile(repo):
    """The Dragonair of the issue: two printings, two rows, one card."""
    repo.upsert_collection_item({"card_id": "bs-18", "condition": "M/NM"})
    repo.upsert_collection_item({"card_id": "b2-22", "condition": "EX"})

    rows, total = repo.list_collection()
    assert total == 1 and _cards(rows) == ["bs-18"], "the M/NM copy represents it"
    assert rows[0]["group_quantity"] == 2
    assert set(rows[0]["group_card_ids"]) == {"bs-18", "b2-22"}


def test_two_grades_of_one_printing_are_one_tile(repo):
    """The Hitmonchan case: one card_id, two rows, still one card."""
    repo.upsert_collection_item({"card_id": "bs-7", "condition": "GD"})
    repo.upsert_collection_item({"card_id": "bs-7", "condition": "EX"})

    rows, total = repo.list_collection()
    assert total == 1 and rows[0]["condition"] == "EX"
    assert rows[0]["group_quantity"] == 2


def test_the_same_name_by_another_illustrator_stays_its_own_tile(repo):
    """Reprints share the artwork. Two Hitmonchans drawn by different people are
    two cards, and merging them would hide one of them entirely."""
    repo.upsert_collection_item({"card_id": "bs-7"})
    repo.upsert_collection_item({"card_id": "b2-8"})

    rows, total = repo.list_collection()
    assert total == 2 and sorted(_cards(rows)) == ["b2-8", "bs-7"]


def test_quantity_on_one_row_still_counts(repo):
    """A single row of two copies was always badged x2; it still is."""
    repo.upsert_collection_item({"card_id": "bs-7", "quantity": 2})
    rows, _ = repo.list_collection()
    assert rows[0]["group_quantity"] == 2 and rows[0]["group_rows"] == 1


# ------------------------------------------------------------- the photo ---
def test_the_tile_shows_the_best_copy_photo_across_printings(repo, tmp_path):
    """"Prioritise the photo of the copy in the best grade" — even when that
    copy is a different printing than the one with a photo attached."""
    repo.upsert_collection_item({"card_id": "bs-18", "condition": "M/NM"})
    repo.upsert_collection_item({"card_id": "b2-22", "condition": "EX"})
    nm = next(i for i in repo.items_by_card("bs-18") if i["card_id"] == "bs-18")
    repo.add_photo(nm["id"], {"filename": "nm.jpg", "is_primary": 1})

    rows, _ = repo.list_collection()
    assert rows[0]["display_photo"]["filename"] == "nm.jpg"


def test_a_worse_copy_photo_beats_no_photo(repo):
    """The best copy has no photo of its own, so the tile shows the one photo
    that exists rather than falling back to catalog art."""
    repo.upsert_collection_item({"card_id": "bs-18", "condition": "M/NM"})
    repo.upsert_collection_item({"card_id": "b2-22", "condition": "EX"})
    ex = next(i for i in repo.items_by_card("b2-22"))
    repo.add_photo(ex["id"], {"filename": "ex.jpg", "is_primary": 1})

    rows, _ = repo.list_collection()
    assert rows[0]["card_id"] == "bs-18", "still represented by the M/NM copy"
    assert rows[0]["display_photo"]["filename"] == "ex.jpg"


# ------------------------------------------------------------- the price ---
def test_the_tile_is_worth_every_copy_it_shows(app):
    """A tile reading x2 has to be worth two cards, each priced as its own
    printing — 14.31 for the Base one plus 7.64 for the Base Set 2 one. Pricing
    the shown row alone lost the other copy from the collection's value."""
    _own(app.repo, "bs-18", condition="M/NM")
    _own(app.repo, "b2-22", condition="M/NM")
    PricingService(app.repo, Config).refresh()

    row = app.test_client().get("/api/collection").get_json()["data"][0]
    assert row["value"]["total"] == pytest.approx(21.95)
    assert row["value"]["partial"] is False


def test_a_worse_grade_is_priced_as_its_own_grade(app):
    """Each copy keeps its own condition factor: EX is 0.85 of the printing."""
    _own(app.repo, "bs-18", condition="M/NM")
    _own(app.repo, "b2-22", condition="EX")
    PricingService(app.repo, Config).refresh()

    row = app.test_client().get("/api/collection").get_json()["data"][0]
    assert row["value"]["total"] == pytest.approx(14.31 + 6.49)


def test_an_unpriced_copy_makes_the_total_a_floor(app):
    """One copy pinned no printing, so it has no price and the sum is not the
    tile's value. Saying so beats passing a short number off as the whole."""
    app.repo.upsert_cards([{"id": "b2-9", "official_set_id": "b2",
                            "name": "Dragonair", "number": "9",
                            "rarity": "Rare", "artist": "Mitsuhiro Arita"}])
    _own(app.repo, "bs-18", condition="M/NM")
    _own(app.repo, "b2-9", condition="M/NM")
    PricingService(app.repo, Config).refresh()

    rows = app.test_client().get("/api/collection").get_json()["data"]
    tile = next(r for r in rows if r["card_id"] == "bs-18")
    assert tile["value"]["total"] == pytest.approx(14.31)
    assert tile["value"]["partial"] is True


# -------------------------------------------------------------- the modal ---
def test_the_modal_lists_the_copies_the_tile_counted(app):
    """The half of the bug that "peor aun" refers to: the tile said two copies
    and the modal opened on the other printing showed one. The grid asks for
    the group it collapsed, so either card gives the same two rows."""
    repo = app.repo
    repo.upsert_collection_item({"card_id": "bs-18", "condition": "M/NM"})
    repo.upsert_collection_item({"card_id": "b2-22", "condition": "EX"})
    client = app.test_client()

    for card_id in ("bs-18", "b2-22"):
        rows = client.get(
            f"/api/collection/by-card/{card_id}?reprints=1").get_json()["data"]
        assert {r["card_id"] for r in rows} == {"bs-18", "b2-22"}


def test_the_modal_stays_strict_by_default(app):
    """Without the flag nothing changes: the Sets page opens a card you do not
    own and must not be shown a reprint as if you did."""
    app.repo.upsert_collection_item({"card_id": "b2-22"})
    rows = app.test_client().get(
        "/api/collection/by-card/bs-18").get_json()["data"]
    assert rows == []


# ------------------------------------------------------------- the filters --
def test_the_quantity_filter_counts_the_whole_tile(repo):
    """"2 o mas" asks about the card the tile shows. Counting one printing at a
    time hid the x2 Dragonair from its own filter."""
    repo.upsert_collection_item({"card_id": "bs-18"})
    repo.upsert_collection_item({"card_id": "b2-22"})
    rows, total = repo.list_collection(min_quantity=2)
    assert total == 1 and rows[0]["card_id"] == "bs-18"


def test_filtering_to_one_printing_shows_only_that_copy(repo):
    """Filters run before the collapse, so narrowing to one set narrows the
    tile too — a Base Set 2 filter must not show a Base Set copy or its price."""
    repo.upsert_collection_item({"card_id": "bs-18", "condition": "M/NM"})
    repo.upsert_collection_item({"card_id": "b2-22", "condition": "EX"})

    rows, total = repo.list_collection(condition="EX")
    assert total == 1 and rows[0]["card_id"] == "b2-22"
    assert rows[0]["group_quantity"] == 1


def test_paging_counts_tiles_not_rows(repo):
    """The count under the toolbar has to be the number of tiles, or the last
    page comes back empty."""
    repo.upsert_collection_item({"card_id": "bs-18"})
    repo.upsert_collection_item({"card_id": "b2-22"})
    repo.upsert_collection_item({"card_id": "bs-7"})

    rows, total = repo.list_collection(page_size=1)
    assert total == 2 and len(rows) == 1
    page2, _ = repo.list_collection(page=2, page_size=1)
    assert len(page2) == 1 and page2[0]["card_id"] != rows[0]["card_id"]


def test_sorting_by_quantity_uses_the_whole_tile(repo):
    """The badge counts every copy, so the sort has to as well."""
    repo.upsert_collection_item({"card_id": "bs-7"})
    repo.upsert_collection_item({"card_id": "bs-18"})
    repo.upsert_collection_item({"card_id": "b2-22"})

    rows, _ = repo.list_collection(sort="quantity")
    assert _cards(rows) == ["bs-18", "bs-7"]


# ------------------------------------------------- the all-cards view mode --
def test_all_mode_draws_a_slot_once_however_many_copies(repo):
    """Same defect on the other toggle: a slot owned in two grades drew two
    tiles and made the set look bigger than it is."""
    repo.upsert_collection_set({"id": "base", "name": "Base",
                                "rules_json": '{"include_sets": ["bs"]}'})
    SetBuilder(repo).build("base")
    repo.upsert_collection_item({"card_id": "bs-7", "condition": "GD"})
    repo.upsert_collection_item({"card_id": "bs-7", "condition": "EX"})

    rows, total = repo.list_slots_with_ownership(set_id="base", page_size=100)
    assert total == 2, "Dragonair and Hitmonchan, once each"
    hitmonchan = next(r for r in rows if r["card_id"] == "bs-7")
    assert hitmonchan["group_quantity"] == 2 and hitmonchan["condition"] == "EX"


def test_all_mode_keeps_unowned_slots(repo):
    """Collapsing must not swallow the placeholders — they are the point of the
    view."""
    repo.upsert_collection_set({"id": "base", "name": "Base",
                                "rules_json": '{"include_sets": ["bs"]}'})
    SetBuilder(repo).build("base")
    rows, total = repo.list_slots_with_ownership(set_id="base", page_size=100)
    assert total == 2 and not any(r["owned"] for r in rows)
    assert all(r["group_quantity"] is None for r in rows)


# ------------------------------------------------------------- accounting ---
def test_the_collection_total_still_counts_every_copy(app):
    """Grouping is a fact about the grid, not about the collection. Valuing the
    shown row and calling it the total quietly deleted the folded-away copies
    from what the collection is worth — 20.80 of Dragonair became 14.31."""
    _own(app.repo, "bs-18", condition="M/NM")
    _own(app.repo, "b2-22", condition="M/NM")
    _own(app.repo, "bs-7", condition="M/NM")
    PricingService(app.repo, Config).refresh()

    value = PricingService(app.repo, Config).value_collection()
    assert value["total_eur"] == pytest.approx(14.31 + 7.64 + 12.57)
    assert value["priced_items"] == 3


def test_each_copy_is_filed_under_its_own_set(app):
    """The per-set breakdown has to put the Base Set 2 reprint under Base Set 2,
    not under the printing that happens to represent the tile."""
    _own(app.repo, "bs-18", condition="M/NM")
    _own(app.repo, "b2-22", condition="M/NM")
    PricingService(app.repo, Config).refresh()

    by_set = PricingService(app.repo, Config).value_collection()["by_official_set"]
    assert by_set == {"bs": pytest.approx(14.31), "b2": pytest.approx(7.64)}


def test_top_value_ranks_a_card_at_what_every_copy_is_worth(app):
    """One entry per card, worth all its copies — listing rows entered a card
    owned twice twice over, and pricing one row ranked it below its worth."""
    _own(app.repo, "bs-18", condition="M/NM")
    _own(app.repo, "b2-22", condition="M/NM")
    _own(app.repo, "bs-7", condition="M/NM")
    PricingService(app.repo, Config).refresh()

    top = app.test_client().get("/api/dashboard").get_json()["top_value"]
    assert [t["card_id"] for t in top] == ["bs-18", "bs-7"]
    assert top[0]["value"] == pytest.approx(21.95) and top[0]["quantity"] == 2
