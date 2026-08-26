import json

from flask import Blueprint, jsonify, request

from . import cfg, page_response, paginate_args, repo, svc
from .. import ApiError
from ..services.market import attach, market_url

bp = Blueprint("catalog", __name__, url_prefix="/api")


@bp.get("/healthz")
def healthz():
    r = repo()
    return jsonify({"ok": True, "cards": r.count_cards(),
                    "schema_version": r.get_meta("schema_version")})


@bp.get("/meta")
def meta():
    """Vocabularies the UI needs, so the front end never hardcodes them."""
    from ..config import (CONDITIONS, CONDITION_LABELS, LANGUAGES, LANGUAGE_LABELS,
                          RATING_LABELS, VARIANTS, VARIANT_LABELS)
    r = repo()
    return jsonify({
        "conditions": [{"key": k, "label": CONDITION_LABELS[k]} for k in CONDITIONS],
        "languages": [{"key": k, "label": LANGUAGE_LABELS[k]} for k in LANGUAGES],
        "variants": [{"key": k, "label": VARIANT_LABELS[k]} for k in VARIANTS],
        "rarities": r.rarities(),
        "types": r.card_types(),
        "editions": [{"key": "first_edition", "label": "1st Edition"},
                     {"key": "unlimited", "label": "Unlimited"}],
        "ratings": [{"value": v, "label": lbl} for v, lbl in
                    sorted(RATING_LABELS.items())],
        "official_sets": r.list_official_sets(),
        "last_price_refresh": r.get_meta("last_price_refresh"),
    })


@bp.get("/cards")
def list_cards():
    page, size = paginate_args()
    rows, total = repo().search_cards(
        q=request.args.get("q", ""),
        official_set=request.args.get("set", ""),
        rarity=request.args.get("rarity", ""),
        page=page, page_size=size,
    )
    return page_response(attach(rows, locale=cfg().CARDMARKET_LOCALE), total, page, size)


@bp.get("/cards/<card_id>")
def get_card(card_id):
    card = repo().get_card(card_id)
    if not card:
        raise ApiError("carta no encontrada", "not_found", 404)
    card["items"] = repo().items_by_card(card_id)
    card["prices"] = repo().get_prices_for_card(card_id)
    card["market_url"] = market_url(card, locale=cfg().CARDMARKET_LOCALE)
    # Empty when the card has no sibling printings, so the UI can skip the
    # edition selector rather than showing a one-option dropdown.
    printings = repo().printings_for_card(card_id)
    # Parse the variant list so the client does not have to, and fall back to the
    # era rules for a card that has no printing row of its own.
    for pr in printings:
        pr["variants"] = json.loads(pr.get("variants_json") or "[]")
    if not printings:
        from ..services.printing_variants import variants_for
        printings = [{
            "id": None, "card_id": card_id,
            "official_set_id": card["official_set_id"],
            "display_name": card.get("set_name"), "is_reprint": 0,
            "variants": variants_for(card["official_set_id"], card.get("rarity")),
            "source": "single",
        }]
    card["available_printings"] = printings
    card["rating"] = repo().get_card_rating(card_id)
    card["target"] = repo().get_card_target(card_id)
    return jsonify(card)


@bp.put("/cards/<card_id>/target")
def set_card_target(card_id):
    """How many copies of this card count as complete.

    Belongs to the card, like the rank: wanting three Charizards is a statement
    about the card, not about any one copy.
    """
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    body = request.get_json(silent=True) or {}
    try:
        target = int(body.get("target"))
    except (TypeError, ValueError):
        raise ApiError("el objetivo debe ser un entero >= 1", "invalid_target") from None
    if target < 1:
        raise ApiError("el objetivo debe ser al menos 1", "invalid_target")
    repo().set_card_target(card_id, target)
    return jsonify({"card_id": card_id, "target": repo().get_card_target(card_id)})


@bp.put("/cards/<card_id>/rating")
def set_card_rating(card_id):
    """Hall of Fame rank for the card itself.

    It lived on the collection row, which meant ranking the holo and the non-holo
    of one card separately — two answers to a question that has one.
    """
    from ..config import MAX_RATING
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    body = request.get_json(silent=True) or {}
    try:
        rating = int(body.get("rating"))
    except (TypeError, ValueError):
        raise ApiError(f"el rating debe ser un entero entre 0 y {MAX_RATING}",
                       "invalid_rating") from None
    if not 0 <= rating <= MAX_RATING:
        raise ApiError(f"el rating debe estar entre 0 y {MAX_RATING}", "invalid_rating")
    repo().set_card_rating(card_id, rating)
    return jsonify({"card_id": card_id, "rating": repo().get_card_rating(card_id)})


@bp.get("/search")
def search():
    """Global search across catalog and collection (spec §19).

    A rating filter narrows the collection half only — the catalog has no ranks,
    and silently dropping catalog hits when one is set would look like the search
    was broken.
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"cards": [], "collection": []})

    from .collection import _rating_arg
    rating = _rating_arg("rating")
    rating_min = _rating_arg("rating_min")
    rating_max = _rating_arg("rating_max")

    cards, _ = repo().search_cards(q=q, page=1, page_size=25)
    items, _ = repo().list_collection(
        q=q, rating=rating, rating_min=rating_min, rating_max=rating_max,
        page=1, page_size=25)
    return jsonify({"cards": attach(cards, locale=cfg().CARDMARKET_LOCALE),
                    "collection": items})


@bp.post("/catalog/import")
def import_catalog():
    """Long-running: kept as an explicit POST, not something a page load triggers."""
    body = request.get_json(silent=True) or {}
    set_ids = body.get("sets")
    if not set_ids:
        from ..services.seed_sets import required_official_sets
        set_ids = required_official_sets()
    result = svc("importer").import_sets(set_ids)
    if body.get("cache_images", True):
        result["images"] = svc("importer").cache_images()
    if body.get("resolve_links", True):
        result["market_links"] = svc("importer").resolve_market_links()
    return jsonify(result)
