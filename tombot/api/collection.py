from flask import Blueprint, jsonify, request

from . import cfg, paginate_args, repo, svc
from .. import ApiError
from ..config import CONDITIONS, LANGUAGES, MAX_RATING, VARIANTS
from ..services.images import ImageError, delete_files, process_upload
from ..services.market import market_url

bp = Blueprint("collection", __name__, url_prefix="/api/collection")


def _validate(body: dict) -> None:
    if body.get("variant") and body["variant"] not in VARIANTS:
        raise ApiError(f"variante inválida: {body['variant']}")
    if body.get("condition") and body["condition"] not in CONDITIONS:
        raise ApiError(f"condición inválida: {body['condition']}")
    if body.get("language") and body["language"] not in LANGUAGES:
        raise ApiError(f"idioma inválido: {body['language']}")
    if "quantity" in body and int(body["quantity"]) < 1:
        raise ApiError("la cantidad debe ser >= 1")
    if body.get("printing_id") is not None:
        printing = repo().get_printing(int(body["printing_id"]))
        if not printing:
            raise ApiError("edición no encontrada", "invalid_printing", 404)
        # card_id and printing_id must agree, or the collection would claim a
        # printing that belongs to a different card.
        if body.get("card_id") and body["card_id"] != printing["card_id"]:
            raise ApiError("la edición no corresponde a esta carta", "invalid_printing")
        body["card_id"] = printing["card_id"]
    if body.get("rating") is not None:
        try:
            rating = int(body["rating"])
        except (TypeError, ValueError):
            raise ApiError("el rating debe ser un entero entre 0 y 8",
                           "invalid_rating") from None
        if not 0 <= rating <= MAX_RATING:
            raise ApiError(f"el rating debe estar entre 0 y {MAX_RATING}",
                           "invalid_rating")
        body["_rating"] = rating       # applied to the card, not the row


def _rating_arg(name: str) -> int | None:
    """Parse a rating query parameter, rejecting out-of-range values.

    Silently ignoring a bad value would quietly return the unfiltered collection,
    which reads as "the filter does nothing" rather than "that was invalid".
    """
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(f"{name} debe ser un entero entre 0 y {MAX_RATING}",
                       "invalid_rating") from None
    if not 0 <= value <= MAX_RATING:
        raise ApiError(f"{name} debe estar entre 0 y {MAX_RATING}", "invalid_rating")
    return value


def _priced(rows):
    pricing = svc("pricing")
    mods = repo().get_modifiers()
    locale = cfg().CARDMARKET_LOCALE
    # Grid art comes from the best-conditioned copy of the card, which may live
    # on a different row than the one being rendered.
    best = repo().best_photos_for_cards([r["card_id"] for r in rows if r.get("card_id")])
    # The card's direct Cardmarket product match, for rows that never pinned an
    # exact version. Replaces the old card-level redirector, which now only 404s
    # (issue #27). One lookup for the whole page.
    by_card = repo().market_urls_for_cards([r["card_id"] for r in rows if r.get("card_id")])
    for r in rows:
        r["display_photo"] = best.get(r["card_id"]) if r.get("owned", True) else None
        # A placeholder has no physical copy, so it has no estimated value —
        # pricing it would invent a number for a card that is not owned.
        r["value"] = (pricing.estimate_item(r, mods) if r.get("owned", True)
                      else {"unit": None, "total": None, "currency": "EUR",
                            "basis": "not_owned", "updated_at": None})
        r["market_url"] = market_url(r, locale=locale) or by_card.get(r.get("card_id"))

    # A row that chose a version knows its exact Cardmarket product, so its link
    # is that product's URL — not the card-level match, which pointed a Normal
    # Flareon at the Holo listing (issue #27). One lookup for the whole page.
    product_ids = [r["market_product_id"] for r in rows if r.get("market_product_id")]
    if product_ids:
        products = repo().market_products_by_ids(product_ids)
        for r in rows:
            pid = r.get("market_product_id")
            prod = products.get(pid) if pid else None
            if prod and prod.get("market_url"):
                r["market_url"] = prod["market_url"]
    return rows


def _truthy(name: str) -> bool:
    return (request.args.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


@bp.get("")
def list_items():
    """Owned inventory, or every card in the personal sets when show_all=1.

    show_all keeps the same shape and filters so the front end can flip modes
    without a second code path; unowned rows come back with owned=false and no
    collection fields.
    """
    page, size = paginate_args()

    if _truthy("show_all"):
        rows, total = repo().list_slots_with_ownership(
            q=request.args.get("q", ""),
            set_id=request.args.get("set", ""),
            condition=request.args.get("condition", ""),
            variant=request.args.get("variant", ""),
            language=request.args.get("language", ""),
            rarity=request.args.get("rarity", ""),
            card_type=request.args.get("type", ""),
            edition=request.args.get("edition", ""),
            min_quantity=request.args.get("min_quantity", type=int),
            rating=_rating_arg("rating"),
            rating_min=_rating_arg("rating_min"),
            rating_max=_rating_arg("rating_max"),
            sort=request.args.get("sort", "set"),
            page=page, page_size=size,
        )
        return jsonify({
            "data": _priced(rows), "page": page, "page_size": size, "total": total,
            "mode": "all",
            "totals": {**repo().collection_totals(),
                       **repo().slots_ownership_totals(request.args.get("set", ""))},
        })

    rows, total = repo().list_collection(
        q=request.args.get("q", ""),
        set_id=request.args.get("set", ""),
        condition=request.args.get("condition", ""),
        variant=request.args.get("variant", ""),
        language=request.args.get("language", ""),
        rarity=request.args.get("rarity", ""),
        card_type=request.args.get("type", ""),
        edition=request.args.get("edition", ""),
        min_quantity=request.args.get("min_quantity", type=int),
        rating=_rating_arg("rating"),
        rating_min=_rating_arg("rating_min"),
        rating_max=_rating_arg("rating_max"),
        sort=request.args.get("sort", "set"),
        page=page, page_size=size,
    )
    return jsonify({
        "data": _priced(rows), "page": page, "page_size": size, "total": total,
        "mode": "owned",
        # Unique vs physical counts, shown side by side.
        "totals": repo().collection_totals(),
    })


@bp.get("/<int:item_id>")
def get_item(item_id):
    row = repo().get_collection_item(item_id)
    if not row:
        raise ApiError("registro no encontrado", "not_found", 404)
    return jsonify(_priced([row])[0])


@bp.get("/by-card/<card_id>")
def by_card(card_id):
    """All physical variants held for one logical card — powers the modal."""
    return jsonify({"data": _priced(repo().items_by_card(card_id))})


@bp.post("")
def add_item():
    body = request.get_json(silent=True) or {}
    if not body.get("card_id"):
        raise ApiError("card_id es obligatorio")
    if not repo().get_card(body["card_id"]):
        raise ApiError("carta no encontrada en el catálogo", "not_found", 404)
    _validate(body)
    # mode=add increments an existing (card, variant, condition, language) row
    # instead of creating a duplicate that would double the physical count.
    mode = body.get("mode", "add")
    item = repo().upsert_collection_item(body, mode=mode)
    # The rank belongs to the card, so a rating sent with a collection write is
    # applied there. Kept working rather than rejected: it is a natural thing to
    # send when registering a card you already have an opinion about.
    if "_rating" in body:
        repo().set_card_rating(item["card_id"], body["_rating"])
        item["rating"] = body["_rating"]
    return jsonify(item), 201


@bp.put("/<int:item_id>")
def update_item(item_id):
    if not repo().get_collection_item(item_id):
        raise ApiError("registro no encontrado", "not_found", 404)
    body = request.get_json(silent=True) or {}
    _validate(body)
    current = repo().get_collection_item(item_id)
    if "_rating" in body:
        repo().set_card_rating(current["card_id"], body["_rating"])
    return jsonify(repo().update_collection_item(item_id, body))


@bp.delete("/<int:item_id>")
def delete_item(item_id):
    if not repo().get_collection_item(item_id):
        raise ApiError("registro no encontrado", "not_found", 404)
    orphaned = repo().delete_collection_item(item_id)
    delete_files(orphaned, cfg())
    return jsonify({"deleted": item_id, "photos_removed": len(orphaned)})


# ------------------------------------------------------------------- photos
@bp.post("/<int:item_id>/photos")
def upload_photo(item_id):
    if not repo().get_collection_item(item_id):
        raise ApiError("registro no encontrado", "not_found", 404)
    f = request.files.get("photo") or request.files.get("file")
    if not f or not f.filename:
        raise ApiError("no se recibió ninguna imagen")
    try:
        processed = process_upload(f, cfg())
    except ImageError as e:
        raise ApiError(str(e), "invalid_image", 415) from e
    return jsonify(repo().add_photo(item_id, processed)), 201


@bp.put("/photos/<int:photo_id>")
def update_photo(photo_id):
    if not repo().get_photo(photo_id):
        raise ApiError("foto no encontrada", "not_found", 404)
    if (request.get_json(silent=True) or {}).get("is_primary"):
        repo().set_primary_photo(photo_id)
    return jsonify(repo().get_photo(photo_id))


@bp.delete("/photos/<int:photo_id>")
def delete_photo(photo_id):
    if not repo().get_photo(photo_id):
        raise ApiError("foto no encontrada", "not_found", 404)
    delete_files(repo().delete_photo(photo_id), cfg())
    return jsonify({"deleted": photo_id})
