from flask import Blueprint, current_app, jsonify, request

from . import cfg, repo, svc
from .. import ApiError
from ..config import VARIANTS

bp = Blueprint("prices", __name__, url_prefix="/api/prices")


@bp.get("/<card_id>")
def card_prices(card_id):
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    return jsonify({"card_id": card_id,
                    "prices": repo().get_prices_for_card(card_id),
                    "quotes": repo().quotes_for_card(card_id)})


@bp.get("/<card_id>/quotes")
def card_quotes(card_id):
    """Every quote we hold for this card, from every provider and market.

    Deliberately not reduced to one number: two providers quoting the same
    market and disagreeing by several times is the signal that one of them has
    the wrong card, and averaging would bury exactly that.
    """
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    return jsonify({"card_id": card_id,
                    "quotes": repo().quotes_for_card(card_id,
                                                     request.args.get("variant"))})


@bp.post("/refresh")
def refresh():
    """Manual trigger for the same code path the scheduler runs — important
    because the upstream API is flaky and reruns are routine (PLAN.md §2.2)."""
    body = request.get_json(silent=True) or {}
    return jsonify(svc("pricing").refresh(
        stale_days=body.get("stale_days"),
        all_cards=bool(body.get("all", False)),
    ))


@bp.post("/refresh-async")
def refresh_async():
    """Kick off a price refresh and return immediately.

    The synchronous endpoint holds a worker for as long as the upstream takes,
    which is minutes for a full collection.
    """
    started, state = svc("jobs").start(
        "prices", lambda: svc("pricing").refresh(all_cards=True))
    return jsonify({"started": started, **state}), (202 if started else 409)


@bp.get("/history")
def history():
    return jsonify({"data": repo().price_history(
        card_id=request.args.get("card_id"),
        set_id=request.args.get("set_id"),
    )})


@bp.get("/modifiers")
def modifiers():
    return jsonify(repo().get_modifiers())


@bp.put("/modifiers/<kind>/<key>")
def set_modifier(kind, key):
    """Edit a price multiplier.

    The 1st-edition premium lives here because no source prices a 1st edition
    apart from its unstamped twin. One number cannot be right for a Charizard and
    a common at once, so it has to be adjustable.
    """
    if kind not in ("condition", "language", "variant"):
        raise ApiError(f"tipo de multiplicador desconocido: {kind}", "invalid_modifier")
    body = request.get_json(silent=True) or {}
    try:
        value = float(body.get("multiplier"))
    except (TypeError, ValueError):
        raise ApiError("el multiplicador debe ser un número", "invalid_modifier") from None
    if not 0 < value <= 100:
        raise ApiError("el multiplicador debe estar entre 0 y 100", "invalid_modifier")
    repo().set_modifier(kind, key, value)
    return jsonify({"kind": kind, "key": key, "multiplier": value})


@bp.put("/manual/<card_id>/<variant>")
def set_manual(card_id, variant):
    """A price typed in by hand for one printing.

    Needed because the feed has real gaps — every WOTC promo comes back with no
    price at all — and because a listing you are looking at beats an average.
    Stored as its own source so a refresh never overwrites it; sending null
    removes it and hands the printing back to the feed.
    """
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    if variant not in VARIANTS:
        raise ApiError(f"variante inválida: {variant}")
    body = request.get_json(silent=True) or {}
    raw = body.get("price")
    if raw in (None, ""):
        repo().set_manual_price(card_id, variant, None)
        return jsonify({"card_id": card_id, "variant": variant, "price": None})
    try:
        price = float(raw)
    except (TypeError, ValueError):
        raise ApiError("el precio debe ser un número", "invalid_price") from None
    if price < 0:
        raise ApiError("el precio no puede ser negativo", "invalid_price")
    repo().set_manual_price(card_id, variant, price)
    return jsonify({"card_id": card_id, "variant": variant, "price": price})


@bp.get("/versions")
def card_versions():
    """Versions of a card that exist on the market, for the add-card picker.

    Answers the question the old dropdown could not: what can I actually own,
    and what does each one look like. Every row carries the product it maps to,
    so choosing one removes the guessing that used to happen at price time.
    """
    name = (request.args.get("name") or "").strip()
    episode_id = request.args.get("episode_id", type=int)

    # Given a card, work out both from what we already know. The set is what
    # makes the answer complete, so it is resolved here rather than left to the
    # caller to remember.
    card_id = request.args.get("card_id")
    if card_id:
        card = repo().get_card(card_id)
        if not card:
            raise ApiError("carta no encontrada", "not_found", 404)
        name = name or card["name"]
        if episode_id is None:
            episode_id = _episode_for_set(card["official_set_id"])

    if not name:
        raise ApiError("hace falta un nombre o un card_id", "invalid_request")

    source = svc("versions_source")
    if source is None or not source.configured:
        raise ApiError("no hay fuente de versiones configurada (TCGGO_API_KEY)",
                       "not_configured", 503)
    try:
        rows = source.search_versions(
            name,
            number=request.args.get("number"),
            episode_id=episode_id,          # resolved above, not re-read here
        )
    except Exception as e:                                   # noqa: BLE001
        # Includes the daily budget being spent: a clear message beats a 500.
        raise ApiError(str(e), "source_error", 502) from None
    return jsonify({"name": name, "versions": rows})


def _episode_for_set(official_set_id: str) -> int | None:
    """The tcggo episode for one of our sets, looked up once and remembered.

    Costs a request the first time and nothing afterwards, which matters when
    the allowance is 80 a day.
    """
    known = repo().get_set_episode(official_set_id)
    if known:
        return known["episode_id"]

    oset = repo().get_official_set(official_set_id)
    if not oset:
        return None
    source = svc("versions_source")
    if source is None or not source.configured:
        return None
    try:
        episode = source.find_episode(oset["name"], oset.get("ptcgo_code"))
    except Exception:                                        # noqa: BLE001
        # Swallowing this silently is how the set filter came back as "no
        # filter" and returned every Charizard ever printed, which reads like
        # data rather than a failure.
        current_app.logger.warning("episode lookup failed for %s",
                                   official_set_id, exc_info=True)
        return None
    if not episode:
        current_app.logger.warning("no tcggo episode matched set %s (%s)",
                                   official_set_id, oset.get("name"))
    if not episode:
        return None
    repo().set_set_episode(official_set_id, episode["id"],
                           episode.get("name"), episode.get("code"))
    return episode["id"]
