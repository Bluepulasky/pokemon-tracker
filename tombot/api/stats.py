from flask import Blueprint, jsonify

from . import repo, svc

bp = Blueprint("stats", __name__, url_prefix="/api")


@bp.get("/dashboard")
def dashboard():
    """The full dashboard payload in one response."""
    r = repo()
    totals = r.collection_totals()
    progress = r.set_progress()
    for p in progress:
        target = p.get("target") or 0
        owned = p.get("owned") or 0
        p["completion_pct"] = round(100.0 * owned / target, 1) if target else 0.0
        p["missing"] = target - owned
        # Copy progress is a separate question: you can hold every card in a set
        # and still be short of the copies you want.
        held, want = p.get("copies_held") or 0, p.get("copies_target") or 0
        p["copies_pct"] = round(100.0 * held / want, 1) if want else 0.0
        p["copies_missing"] = max(0, want - held)

    target_total = sum(p.get("target") or 0 for p in progress)
    owned_total = sum(p.get("owned") or 0 for p in progress)
    complete_total = sum(p.get("complete") or 0 for p in progress)
    copies_held = sum(p.get("copies_held") or 0 for p in progress)
    copies_target = sum(p.get("copies_target") or 0 for p in progress)
    value = svc("pricing").value_collection()

    by_completion = sorted(progress, key=lambda p: p["completion_pct"], reverse=True)
    by_missing = sorted(progress, key=lambda p: p["missing"], reverse=True)

    return jsonify({
        "unique_cards": totals["unique_cards"],
        "physical_cards": totals["physical_cards"],
        "sets_total": len(progress),
        "sets_complete": sum(1 for p in progress
                             if p["target"] and p.get("complete") == p["target"]),
        # Unique completion: do I have the card at all.
        "completion_pct": round(100.0 * owned_total / target_total, 1) if target_total else 0.0,
        # Copy completion: do I have as many as I set out to.
        "copies_pct": round(100.0 * copies_held / copies_target, 1) if copies_target else 0.0,
        "copies_held": copies_held,
        "copies_target": copies_target,
        "complete_cards": complete_total,
        "target_cards": target_total,
        "owned_cards": owned_total,
        "value": value,
        "sets": progress,
        "most_complete": by_completion[:5],
        "most_missing": by_missing[:5],
        "top_value": _top_value(),
        "last_price_refresh": r.get_meta("last_price_refresh"),
    })


def _top_value(limit: int = 10):
    r = repo()
    pricing = svc("pricing")
    rows, _ = r.list_collection(page=1, page_size=500)
    valued = []
    for row in rows:
        est = pricing.estimate_item(row)
        if est["total"] is not None:
            valued.append({"card_id": row["card_id"], "name": row["name"],
                           "number": row["number"], "set_name": row.get("set_name"),
                           "variant": row["variant"], "condition": row["condition"],
                           "quantity": row["quantity"], "value": est["total"]})
    return sorted(valued, key=lambda v: v["value"], reverse=True)[:limit]


@bp.get("/stats/history")
def history():
    """Collection evolution. Comes from snapshots, because current
    state cannot answer 'how many did I own in March'."""
    return jsonify({"data": list(reversed(repo().list_snapshots()))})
