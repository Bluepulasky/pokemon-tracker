import json

from flask import Blueprint, jsonify, request

from . import repo, svc
from .. import ApiError

bp = Blueprint("sets", __name__, url_prefix="/api/sets")


def _with_progress(rows):
    for r in rows:
        target = r.get("target") or 0
        r["completion_pct"] = round(100.0 * (r.get("owned") or 0) / target, 1) if target else 0.0
    return rows


@bp.get("")
def list_sets():
    from ..services.tcg_series import series_for_date
    sets_by_id = {s["id"]: s for s in repo().list_collection_sets()}
    rows = _with_progress(repo().set_progress())
    for r in rows:
        r["description"] = (sets_by_id.get(r["id"]) or {}).get("description")
        # The era is derived from the release date, not from tcggo's own series
        # field, which is too sparse to group by (it left most sets blank, which
        # turned every one of them into its own header).
        r["series"] = series_for_date(r.get("release_date"))
    return jsonify({"data": rows})


@bp.get("/<set_id>")
def get_set(set_id):
    cset = repo().get_collection_set(set_id)
    if not cset:
        raise ApiError("set no encontrado", "not_found", 404)
    progress = _with_progress(repo().set_progress(set_id))
    cset["progress"] = progress[0] if progress else None
    cset["slots"] = repo().get_set_slots(set_id)
    # The whole set, each card flagged collecting/owned, for a single grid with
    # per-card toggles rather than a rule-filtered subset.
    cset["cards"] = repo().set_cards_with_state(set_id)
    return jsonify(cset)


@bp.get("/<set_id>/missing")
def missing(set_id):
    if not repo().get_collection_set(set_id):
        raise ApiError("set no encontrado", "not_found", 404)
    return jsonify({"data": repo().missing_slots(set_id, request.args.get("sort", "number"))})


@bp.post("")
def create_set():
    body = request.get_json(silent=True) or {}
    if not body.get("id") or not body.get("name"):
        raise ApiError("id y name son obligatorios")
    _save(body)
    return jsonify(repo().get_collection_set(body["id"])), 201


@bp.put("/<set_id>/hidden")
def set_hidden(set_id):
    """Hide a set from the Sets page and the completion totals, or show it again.

    The set keeps everything — cards, products, the goal — so this is not a
    delete: it is for sets added by accident or while testing that should not
    count. Hidden sets are un-hidden from Mantenimiento, so hiding one from the
    grid is one click and costs nothing to reverse.
    """
    if not repo().get_collection_set(set_id):
        raise ApiError("set no encontrado", "not_found", 404)
    hidden = bool((request.get_json(silent=True) or {}).get("hidden", True))
    repo().set_hidden(set_id, hidden)
    return jsonify({"set_id": set_id, "hidden": hidden})


@bp.put("/<set_id>")
def update_set(set_id):
    if not repo().get_collection_set(set_id):
        raise ApiError("set no encontrado", "not_found", 404)
    body = request.get_json(silent=True) or {}
    body["id"] = set_id
    _save(body)
    return jsonify(repo().get_collection_set(set_id))


def _save(body):
    rules = body.get("rules")
    repo().upsert_collection_set({
        "id": body["id"],
        "name": body.get("name") or body["id"],
        "description": body.get("description"),
        "group_name": body.get("group_name"),
        "position": int(body.get("position", 0)),
        "rules_json": json.dumps(rules) if rules is not None else body.get("rules_json"),
    })


@bp.delete("/<set_id>")
def delete_set(set_id):
    repo().delete_collection_set(set_id)
    return jsonify({"deleted": set_id})


@bp.post("/<set_id>/rebuild")
def rebuild(set_id):
    """Re-materialise slots from rules_json. Manual slots survive."""
    return jsonify(svc("setbuilder").build(set_id))


# The collection rule is a call on the set's completion state, kept separate
# from the set itself: the catalogue is always the whole set, and the rule
# decides which of it you are trying to complete. Named modes keep the common
# choices one click away; the rule underneath stays fully editable.
COLLECTION_MODES = {
    "all":        {"label": "Todas"},
    "no-holos":   {"label": "Sin holos",  "exclude_rarities": ["Rare Holo"]},
    "holos-only": {"label": "Solo holos", "include_rarities": ["Rare Holo"]},
    "no-commons": {"label": "Sin comunes", "exclude_rarities": ["Common"]},
}


@bp.put("/<set_id>/card/<card_id>")
def set_card_override(set_id, card_id):
    """A per-card exception on top of the collection rule.

    The dropdown decides most of a set by rarity, but rarity is a blunt tool:
    Neo Genesis Metal Energy is a Rare Holo you still want under "sin holos".
    So a card can be forced in ("keep") or forced out ("drop") regardless of the
    rule, or returned to whatever the rule says ("reset").

    These overrides live in the rule (include_cards / exclude_cards) and survive
    a mode change — switching sin holos ↔ todas does not lose them.
    """
    cset = repo().get_collection_set(set_id)
    if not cset:
        raise ApiError("set no encontrado", "not_found", 404)
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    action = (request.get_json(silent=True) or {}).get("action")
    if action not in ("keep", "drop", "reset"):
        raise ApiError("acción inválida (keep | drop | reset)", "invalid_action")

    rules = json.loads(cset.get("rules_json") or "{}")
    keep = [c for c in (rules.get("include_cards") or []) if c != card_id]
    drop = [c for c in (rules.get("exclude_cards") or []) if c != card_id]
    if action == "keep":
        keep.append(card_id)
    elif action == "drop":
        drop.append(card_id)
    # reset leaves both cleaned of this card

    rules["include_cards"] = keep
    rules["exclude_cards"] = drop
    repo().upsert_collection_set({
        "id": set_id, "name": cset["name"], "description": cset.get("description"),
        "group_name": cset.get("group_name"), "position": cset.get("position", 0),
        "rules_json": json.dumps(rules),
    })
    built = svc("setbuilder").build(set_id)
    return jsonify({"set_id": set_id, "card_id": card_id, "action": action,
                    "slots": built.get("slots") if isinstance(built, dict) else built})


BULK_SELECTORS = ("all", "holo", "non-holo", "none", "invert")


def _is_holo(card) -> bool:
    """The same holo test the card grid uses (rarity contains 'holo'), so a
    quick-select lands on exactly the cards the stars show as holo — not on an
    exact rarity string, which tcggo spells three different ways."""
    return "holo" in (card.get("rarity") or "").lower()


@bp.put("/<set_id>/collect")
def bulk_collect(set_id):
    """Set the whole set's collecting selection in one move.

    The per-card star is precise but slow across a hundred cards; this is the
    "how do I want to collect this set" shortcut behind it — only holos, only
    non-holos, everything, nothing, or flip what is selected now.

    It materialises to the same place a per-card toggle writes (exclude_cards),
    with the rarity rule cleared, so the result is exactly the chosen set and
    survives a rebuild. Because it computes holo the way the grid displays it,
    "Solo holo" selects precisely the cards showing a filled star as holo.
    """
    cset = repo().get_collection_set(set_id)
    if not cset:
        raise ApiError("set no encontrado", "not_found", 404)
    selector = (request.get_json(silent=True) or {}).get("selector")
    if selector not in BULK_SELECTORS:
        raise ApiError(f"selección inválida ({' | '.join(BULK_SELECTORS)})",
                       "invalid_selector")

    cards = repo().set_cards_with_state(set_id)
    all_ids = {c["id"] for c in cards}
    if selector == "all":
        target = set(all_ids)
    elif selector == "holo":
        target = {c["id"] for c in cards if _is_holo(c)}
    elif selector == "non-holo":
        target = {c["id"] for c in cards if not _is_holo(c)}
    elif selector == "none":
        target = set()
    else:  # invert: whatever is not collecting now becomes collecting
        target = {c["id"] for c in cards if not c["collecting"]}

    # The selection is carried entirely by exclude_cards over the untouched
    # source sets: kept = candidates - exclude_cards when no rarity rule applies.
    rules = json.loads(cset.get("rules_json") or "{}")
    new_rules = {"include_sets": rules.get("include_sets") or []}
    if rules.get("merge"):
        new_rules["merge"] = rules["merge"]
    new_rules["exclude_cards"] = sorted(all_ids - target)

    repo().upsert_collection_set({
        "id": set_id, "name": cset["name"], "description": cset.get("description"),
        "group_name": cset.get("group_name"), "position": cset.get("position", 0),
        "rules_json": json.dumps(new_rules),
    })
    built = svc("setbuilder").build(set_id)
    return jsonify({"set_id": set_id, "selector": selector,
                    "collecting": len(target),
                    "slots": built.get("slots") if isinstance(built, dict) else built})


@bp.get("/<set_id>/mode")
def get_mode(set_id):
    """Which named mode the set's current rule matches, if any."""
    cset = repo().get_collection_set(set_id)
    if not cset:
        raise ApiError("set no encontrado", "not_found", 404)
    rules = json.loads(cset.get("rules_json") or "{}")
    excl = set(rules.get("exclude_rarities") or [])
    incl = set(rules.get("include_rarities") or [])
    current = "custom"
    if not excl and not incl:
        current = "all"
    elif excl == {"Rare Holo"} and not incl:
        current = "no-holos"
    elif incl == {"Rare Holo"} and not excl:
        current = "holos-only"
    elif excl == {"Common"} and not incl:
        current = "no-commons"
    return jsonify({
        "set_id": set_id, "mode": current,
        "options": [{"key": k, "label": v["label"]} for k, v in COLLECTION_MODES.items()],
    })


@bp.put("/<set_id>/mode")
def set_mode(set_id):
    """Change what part of the set you are collecting, and re-materialise slots.

    The set's include_sets are preserved; only the rarity filter changes. Manual
    slots survive the rebuild.
    """
    cset = repo().get_collection_set(set_id)
    if not cset:
        raise ApiError("set no encontrado", "not_found", 404)
    mode = (request.get_json(silent=True) or {}).get("mode")
    if mode not in COLLECTION_MODES:
        raise ApiError(f"modo desconocido: {mode}", "invalid_mode")

    rules = json.loads(cset.get("rules_json") or "{}")
    # Keep what the set is over; replace only the rarity call.
    new_rules = {k: v for k, v in rules.items()
                 if k in ("include_sets", "include_cards", "exclude_cards", "merge")}
    spec = COLLECTION_MODES[mode]
    if spec.get("exclude_rarities"):
        new_rules["exclude_rarities"] = spec["exclude_rarities"]
    if spec.get("include_rarities"):
        new_rules["include_rarities"] = spec["include_rarities"]

    repo().upsert_collection_set({
        "id": set_id, "name": cset["name"], "description": cset.get("description"),
        "group_name": cset.get("group_name"), "position": cset.get("position", 0),
        "rules_json": json.dumps(new_rules),
    })
    built = svc("setbuilder").build(set_id)
    return jsonify({"set_id": set_id, "mode": mode, **built})
