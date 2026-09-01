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
    because the upstream API is flaky and reruns are routine."""
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

    # Imported sets answer locally and cost nothing. Only a set nobody has
    # imported falls through to the API, which is the whole point of importing
    # them: registering a card should not spend an allowance.
    local = _versions_from_import(card_id, episode_id)
    if local is not None:
        return jsonify({"name": name, "versions": local, "source": "local"})

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


def _versions_from_import(card_id: str | None, episode_id: int | None):
    """Every printing of this card, across every set already imported.

    Not just the card's own set: a Pikachu opened from Base Set also lists the
    Jungle and Neo Genesis Pikachu, because the person holding one wants to find
    their exact printing. It costs nothing — reprints are in the database from
    when their set was imported — and each row carries its own card_id and set,
    so a pick records the printing it is, not the card the modal was opened on.

    The card's own set must be imported first (episode_id gate): that is what
    separates "this set was never imported, ask the API" (None) from "imported,
    here is what exists" (a list, possibly with reprints from other sets).
    """
    if not card_id or episode_id is None:
        return None
    if not repo().episode_is_imported(episode_id):
        return None

    card = repo().get_card(card_id)
    if not card:
        return None

    current_set = card["official_set_id"]
    rows = repo().market_products_for_reprint(card_id)
    items = [{
        "market_product_id": r["product_id"],
        "card_id": r["card_id"],
        "name": r["name"], "set": r["set_name"], "set_id": r["set_id"],
        "code": r["code"], "number": r["number"],
        "version": r["version"], "rarity": r["rarity"],
        "image": r["image"], "market_url": r["market_url"],
        "currency": r["currency"], "price": r["price"],
        "lowest_near_mint": r["price_low"], "available": r["available"],
        "is_current": r["set_id"] == current_set,
    } for r in rows]
    # The card's own set first (it is the one the modal was opened on), then the
    # reprints in release order. A stable sort keeps that order within groups.
    items.sort(key=lambda x: 0 if x["is_current"] else 1)
    return items
