"""Fetch new prices: re-import the sets already imported, oldest prices first.

The button and the scheduler used to call PricingService.refresh, which has no
network and only copies what the last import stored. With the HTTP cache never
expiring, that import was itself a replay, so for weeks every "refresh" wrote
September's numbers with today's date (#114). This is the half that talks to
tcggo; the copy into price_cache still runs after it, unchanged.

A full pass over Tom's 21 sets costs about 45 requests against a daily cap of
95, so it fits in one day — but only just with anything else going on, which
is why it stops on its own rather than trying to finish:

* before each set, when the allowance left would not cover one (~6 requests);
* when the allowance runs out or the plan answers 429 partway through a set —
  that set is left exactly as it was, nothing written and nothing pruned;
* on any other error (a 500, a rejected key): it would most likely fail every
  set the same way, and each attempt is billed;
* when a set comes back so much shorter that importing it would delete more
  than a handful of products. Its prices are kept, the deletion is not done,
  and the run stops so a person can look before the next set does the same.

Whatever it does not reach is reported as pending, and since the order is
oldest first, the next run starts there.
"""
from __future__ import annotations

import logging
from datetime import date

from .market_import import ImportInterrupted, MarketImporter

log = logging.getLogger(__name__)

# What one set costs, roughly: Base Set is four pages, most are one or two.
# The same figure the single-set import checks before starting.
SET_COST = 6
# More removals than this from a single set means something upstream is off.
MAX_PRUNE = 10
# price_refresh.py
MIN_AGE_HOURS = 48

def refresh_prices(repo, source, budget, pricing, min_age_hours=MIN_AGE_HOURS) -> dict:
    episodes = repo.episodes_by_price_age(min_age_hours=min_age_hours)
    used_before = budget.used() if budget is not None else 0
    log.info("price refresh: %d sets to renew, %s requests left", len(episodes),
             budget.remaining() if budget is not None else "unlimited")

    importer = MarketImporter(repo, source, budget)
    imported, failed, pending = [], [], []
    stopped = None
    for i, ep in enumerate(episodes):
        if budget is not None and not budget.can_afford(SET_COST):
            stopped = "budget"
            pending = episodes[i:]
            break
        try:
            result = importer.import_episode(ep["episode_id"], fresh=True,
                                             max_prune=MAX_PRUNE)
        except ImportInterrupted as e:
            stopped = e.reason
            pending = episodes[i:]
            break
        except Exception as e:                           # noqa: BLE001
            # Stop rather than move on: a rejected key or an outage would fail
            # every set the same way, and each attempt is a billed request.
            log.warning("price refresh: %s failed: %s", ep.get("name"), e)
            failed.append({"episode_id": ep["episode_id"], "name": ep.get("name"),
                           "error": str(e)})
            stopped = "error"
            pending = episodes[i + 1:]
            break
        imported.append({"episode_id": ep["episode_id"], "name": ep.get("name"),
                         "fetched": result["fetched"], "pruned": result["pruned"],
                         "requests": result["requests"]})
        if result["prune_held"]:
            stopped = "prune_held"
            imported[-1]["prune_held"] = result["prune_held"]
            pending = episodes[i + 1:]
            break

    priced = pricing.refresh()                    # sin red: cubre variantes recién agregadas
    if imported:
        # Only a run that actually fetched something counts as a refresh.
        repo.set_meta("last_price_refresh", date.today().isoformat())

    summary = {
        "imported": imported,
        "failed": failed,
        "pending": [{"episode_id": p["episode_id"], "name": p.get("name")}
                    for p in pending],
        "requests": (budget.used() - used_before) if budget is not None else None,
        "remaining": budget.remaining() if budget is not None else None,
        "stopped": stopped,
        "priced": priced,
        "up_to_date": not episodes,        # todo dentro del umbral
        "min_age_hours": min_age_hours,
    }
    log.info("price refresh: %d sets older than %sh to renew, %s requests left",
             len(episodes), min_age_hours,
             budget.remaining() if budget is not None else "unlimited")
    return summary
