"""TCGdex adapter, driven entirely by recorded API responses.

The fixtures in tests/fixtures/tcgdex/ are real payloads. They exist because the
API is unreachable from the development machine, but they earn their place
regardless: the tests are deterministic, need no network, and pin the exact
shape the adapter was written against.
"""
import json
import pathlib

import pytest

from tombot.services.sources.tcgdex import (
    BASE_FIELDS, REVERSE_FIELDS, parse_variants, price_fields_for,
    variant_key, variant_label,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "tcgdex"


def card(card_id: str) -> dict:
    return json.loads((FIXTURES / f"{card_id}.json").read_text())


def all_cards():
    return [json.loads(f.read_text()) for f in sorted(FIXTURES.glob("*.json"))]


# ------------------------------------------------- the -holo semantics
def test_reverse_reads_the_holo_series():
    """ex7-51 Cubone has NO holo variant — only normal and reverse. Its populated
    `avg-holo` can therefore only be the reverse price."""
    c = card("ex7-51")
    assert c["variants"]["holo"] is False and c["variants"]["reverse"] is True

    got = {v["type"]: v for v in parse_variants(c)}
    assert got["reverse"]["price"] == 49.34     # avg-holo
    assert got["normal"]["price"] == 1.88       # avg
    assert got["reverse"]["price_field"] == "avg-holo"


def test_a_holo_card_reads_the_plain_series():
    """base1-4 Charizard exists only as holo, and its price lives in plain `avg`
    with `avg-holo` null. Reading `-holo` here would return nothing."""
    c = card("base1-4")
    assert c["variants"]["holo"] is True and c["variants"]["reverse"] is False

    unlimited = next(v for v in parse_variants(c) if v["subtype"] == "unlimited")
    assert unlimited["type"] == "holo"
    assert unlimited["price"] == 487.19
    assert unlimited["price_field"] == "avg"


def test_price_fields_by_variant_type():
    assert price_fields_for("reverse") == REVERSE_FIELDS
    for t in ("holo", "normal", "anything-else"):
        assert price_fields_for(t) == BASE_FIELDS


def test_holo_never_reads_the_reverse_series_across_every_fixture():
    """The regression this guards: a Shadowless Charizard reading `avg-holo`
    would come back unpriced instead of EUR 3,091."""
    for c in all_cards():
        for v in parse_variants(c):
            if v["type"] != "reverse" and v["price_field"]:
                assert not v["price_field"].endswith("-holo"), (c["id"], v["key"])


# ------------------------------------------------- print runs and products
def test_unlimited_and_shadowless_are_priced_apart():
    """The whole reason for this source. pokemontcg.io gives one number for both."""
    variants = {v["subtype"]: v for v in parse_variants(card("base1-4"))}
    assert variants["unlimited"]["price"] == 487.19
    assert variants["shadowless"]["price"] == 3091.57
    assert variants["unlimited"]["market_product_id"] != \
           variants["shadowless"]["market_product_id"]


def test_first_edition_always_needs_the_multiplier():
    """No set prices a 1st edition apart from its unstamped twin, so the premium
    can only come from a multiplier."""
    for cid in ("base1-4", "base1-7", "base1-58", "base5-1", "neo1-1", "gym1-1"):
        stamped = [v for v in parse_variants(card(cid))
                   if "1st-edition" in v["stamps"] and v["price"] is not None]
        assert stamped, cid
        for v in stamped:
            assert v["first_edition_multiplier_applies"] is True, (cid, v["key"])


def test_a_single_product_card_shares_its_price_across_printings():
    """Gym Heroes lists a product only under the 1st-edition tag, which would
    otherwise leave an ordinary Blaine's Moltres unpriced. With one product for
    the whole card, that product is the card's price."""
    variants = {tuple(v["stamps"]): v for v in parse_variants(card("gym1-1"))}
    plain, first = variants[()], variants[("1st-edition",)]

    assert plain["price"] == first["price"] == 117.91
    assert plain["price_inherited"] is True, "adopted the card's only product"
    assert first["price_inherited"] is False


def test_multi_product_cards_never_borrow_across_print_runs():
    """The narrowness of the rule above matters: Charizard prices Unlimited and
    Shadowless apart, and must keep doing so."""
    for cid in ("base1-4", "base1-7", "base1-58"):
        variants = parse_variants(card(cid))
        assert not any(v["price_inherited"] for v in variants), cid
    charizard = {v["subtype"]: v for v in parse_variants(card("base1-4"))}
    assert charizard["unlimited"]["price"] != charizard["shadowless"]["price"]
    assert charizard["1999-2000-copyright"]["price"] is None


def test_the_multiplier_flag_is_never_set_without_a_price():
    for c in all_cards():
        for v in parse_variants(c):
            if v["price"] is None:
                assert v["first_edition_multiplier_applies"] is False, (c["id"], v["key"])


def test_missing_prices_are_none_not_zero():
    """Three distinct shapes all mean 'no price': absent `pricing` key, a null
    cardmarket block, and a zeroed field. None may become a number."""
    charizard = {v["subtype"]: v for v in parse_variants(card("base1-4"))}
    assert charizard["1999-2000-copyright"]["price"] is None   # no pricing key

    promo = parse_variants(card("basep-1"))
    assert promo and all(v["price"] is None for v in promo)    # cardmarket null


def test_promos_resolve_but_carry_no_prices():
    """basep-1 exists and its id matches pokemontcg.io, but all 53 WOTC Promos
    would be unpriced from this source."""
    c = card("basep-1")
    assert c["id"] == "basep-1"
    assert c["pricing"]["cardmarket"] is None
    assert all(v["market_product_id"] is None for v in parse_variants(c))


# ------------------------------------------------- keys and labels
def test_variant_keys_are_stable_and_readable():
    keys = {v["key"] for v in parse_variants(card("base1-4"))}
    assert "holo:unlimited" in keys
    assert "holo:shadowless:1st-edition" in keys
    assert "holo:shadowless" in keys


def test_variant_keys_are_unique_within_a_card():
    """Two entries collapsing to one key would silently lose a print run."""
    for c in all_cards():
        keys = [v["key"] for v in parse_variants(c)]
        assert len(keys) == len(set(keys)), (c["id"], keys)


def test_foil_pattern_keeps_printings_distinct():
    """base3-1 has two pre-release printings that differ only by foil pattern.
    Ignoring `foil` collapses them and loses a print run."""
    variants = parse_variants(card("base3-1"))
    prerelease = [v for v in variants if "pre-release" in v["stamps"]]
    assert len(prerelease) == 2
    assert {v["key"] for v in prerelease} == {
        "holo:pre-release:cosmos", "holo:pre-release:starlight"}


def test_non_standard_sizes_are_kept_distinct():
    """base1-58 has a jumbo printing with its own Cardmarket product."""
    variants = {v["key"]: v for v in parse_variants(card("base1-58"))}
    jumbo = [v for k, v in variants.items() if v["size"] == "jumbo"]
    assert len(jumbo) == 1
    assert jumbo[0]["market_product_id"] == 362859
    assert "jumbo" in jumbo[0]["key"]


def test_labels_are_human_readable():
    labels = {v["key"]: v["label"] for v in parse_variants(card("base1-4"))}
    assert labels["holo:shadowless:1st-edition"] == "Shadowless Holo 1St Edition"


# ------------------------------------------------- coverage
def test_every_set_is_covered_by_a_fixture():
    sets = {c["set"]["id"] for c in all_cards()}
    assert sets == {"base1", "base2", "base3", "base5", "basep", "ex7",
                    "gym1", "gym2", "neo1", "neo2", "neo3", "neo4"}


@pytest.mark.parametrize("card_id", sorted(p.stem for p in FIXTURES.glob("*.json")))
def test_every_fixture_parses_without_inventing_prices(card_id):
    variants = parse_variants(card(card_id))
    assert variants, f"{card_id} produced no variants"
    for v in variants:
        assert v["price"] is None or v["price"] > 0
        assert (v["price"] is None) == (v["price_field"] is None)


def test_the_reported_hitmonchan_prices_its_print_runs_apart():
    """The card the whole change started from. Under pokemontcg.io it had one
    price for every print run; here Unlimited and Shadowless differ by 64%."""
    variants = {v["subtype"]: v for v in parse_variants(card("base1-7"))}
    assert variants["unlimited"]["price"] == 14.29
    assert variants["shadowless"]["price"] == 23.5
    assert variants["unlimited"]["market_product_id"] != \
           variants["shadowless"]["market_product_id"]


# ------------------------------------------------- variant resolution
def test_our_variants_map_onto_tcgdex_printings():
    """The collection stores variants in the app's own vocabulary; prices come
    keyed by TCGdex printing. A wrong match here values a Shadowless Charizard as
    an Unlimited one."""
    from tombot.services.variant_map import resolve

    keys = [v["key"] for v in parse_variants(card("base1-7"))]
    assert resolve("holo", keys) == "holo:unlimited"
    assert resolve("shadowless", keys) == "holo:shadowless"
    assert resolve("first_edition", keys) == "holo:shadowless:1st-edition"


def test_unmatched_variants_resolve_to_nothing():
    """No match must mean no price, not the nearest printing."""
    from tombot.services.variant_map import resolve

    keys = [v["key"] for v in parse_variants(card("base1-7"))]
    assert resolve("reverse", keys) is None      # Base Set has no reverse holo
    assert resolve("normal", keys) is None       # this Hitmonchan is holo-only


def test_reverse_resolves_only_to_a_reverse_printing():
    from tombot.services.variant_map import resolve

    keys = [v["key"] for v in parse_variants(card("ex7-51"))]
    assert resolve("reverse", keys) == "reverse:set-logo"
    assert resolve("normal", keys) == "normal"


def test_oddities_are_never_matched_by_a_plain_variant():
    """base1-58 carries a jumbo and a poketour stamp. Asking for a plain normal
    Pikachu must not return either."""
    from tombot.services.variant_map import resolve

    keys = [v["key"] for v in parse_variants(card("base1-58"))]
    assert resolve("normal", keys) == "normal:unlimited"
