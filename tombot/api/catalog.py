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
                          VARIANTS, VARIANT_LABELS)
    r = repo()
    return jsonify({
        "conditions": [{"key": k, "label": CONDITION_LABELS[k]} for k in CONDITIONS],
        "languages": [{"key": k, "label": LANGUAGE_LABELS[k]} for k in LANGUAGES],
        "variants": [{"key": k, "label": VARIANT_LABELS[k]} for k in VARIANTS],
        "rarities": r.rarities(),
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
    return jsonify(card)


@bp.get("/search")
def search():
    """Global search across catalog and collection (spec §19)."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"cards": [], "collection": []})
    cards, _ = repo().search_cards(q=q, page=1, page_size=25)
    items, _ = repo().list_collection(q=q, page=1, page_size=25)
    return jsonify({"cards": cards, "collection": items})


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
