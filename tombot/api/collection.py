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
    if body.get("rating") is not None:
        try:
            rating = int(body["rating"])
        except (TypeError, ValueError):
            raise ApiError("el rating debe ser un entero entre 0 y 8",
                           "invalid_rating") from None
        if not 0 <= rating <= MAX_RATING:
            raise ApiError(f"el rating debe estar entre 0 y {MAX_RATING}",
                           "invalid_rating")


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
    for r in rows:
        r["value"] = pricing.estimate_item(r, mods)
        # The row is a join over cards, so it already carries external_ids_json.
        r["market_url"] = market_url(r, locale=locale)
    return rows


@bp.get("")
def list_items():
    page, size = paginate_args()
    rows, total = repo().list_collection(
        q=request.args.get("q", ""),
        set_id=request.args.get("set", ""),
        condition=request.args.get("condition", ""),
        variant=request.args.get("variant", ""),
        language=request.args.get("language", ""),
        rarity=request.args.get("rarity", ""),
        rating=_rating_arg("rating"),
        rating_min=_rating_arg("rating_min"),
        rating_max=_rating_arg("rating_max"),
        sort=request.args.get("sort", "set"),
        page=page, page_size=size,
    )
    return jsonify({
        "data": _priced(rows), "page": page, "page_size": size, "total": total,
        # Unique vs physical counts, shown side by side per spec §4.
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
    """All physical variants held for one logical card — powers the modal (spec §6)."""
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
    return jsonify(repo().upsert_collection_item(body, mode=mode)), 201


@bp.put("/<int:item_id>")
def update_item(item_id):
    if not repo().get_collection_item(item_id):
        raise ApiError("registro no encontrado", "not_found", 404)
    body = request.get_json(silent=True) or {}
    _validate(body)
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
