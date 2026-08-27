#!/usr/bin/env python3
"""Verify the tcggo key against the live API, spending a fixed, tiny number of requests.

The plan bills per request past a daily allowance, so this is deliberately
boring: it makes exactly two calls, prints what came back, and refuses to run
if the budget cannot cover them.

    TCGGO_API_KEY=... .venv/bin/python scripts/tcggo_live_check.py

It answers the two questions that decide whether we adopt the source:

  1. Does one Cardmarket product belong to exactly one card?
     (TCGdex gives product 273800 to both Jungle Flareons; the non-holo then
     prices four to six times high.)
  2. Are print runs separate cards with their own products?
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_env(path=ROOT / ".env"):
    """Read .env into the environment.

    Docker Compose reads .env by itself, but a script run straight from a shell
    does not, and python-dotenv is not a dependency. Without this the key would
    sit in .env and the script would still report it missing.

    Anything already exported wins, so `TCGGO_API_KEY=... script.py` overrides
    the file rather than being silently ignored.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env()

from tombot.config import Config, DEFAULT_MODIFIERS          # noqa: E402
from tombot.services.budget import BudgetExhausted, RequestBudget  # noqa: E402
from tombot.services.repository import PokemonRepo           # noqa: E402
from tombot.services.sources.tcggo import TcggoSource        # noqa: E402

CALLS = 2

if not Config.TCGGO_API_KEY:
    sys.exit("TCGGO_API_KEY is not set; nothing was sent.")

repo = PokemonRepo(Config.DB_PATH)
repo.init_db(DEFAULT_MODIFIERS)
budget = RequestBudget(repo, "tcggo", Config.TCGGO_DAILY_LIMIT)

print(f"daily cap {budget.limit}, used {budget.used()}, "
      f"remaining {budget.remaining()}")
if not budget.can_afford(CALLS):
    sys.exit(f"needs {CALLS} requests, only {budget.remaining()} left today.")

source = TcggoSource(Config, budget=budget)

print(f"\nspending {CALLS} requests.\n")
try:
    holo = source.fetch_by_tcgid("base2-3")     # Jungle Flareon, holo
    plain = source.fetch_by_tcgid("base2-19")   # Jungle Flareon, non-holo
except BudgetExhausted as e:
    sys.exit(str(e))
except RuntimeError as e:
    sys.exit(f"request failed: {e}")

for label, rows in (("base2-3  Flareon holo", holo),
                    ("base2-19 Flareon plain", plain)):
    print(f"{label}: {len(rows)} printing(s)")
    for r in rows:
        print(f"    version={r['version']!r:26} key={r['key']:22} "
              f"cm={r['market_product_id']} price={r['price']} "
              f"stock={r['available_items']}")

holo_ids = {r["market_product_id"] for r in holo if r["market_product_id"]}
plain_ids = {r["market_product_id"] for r in plain if r["market_product_id"]}
shared = holo_ids & plain_ids

print()
if shared:
    print(f"COLLIDES: both Flareons share product(s) {sorted(shared)} — "
          f"same failure as TCGdex.")
elif holo_ids and plain_ids:
    print(f"CLEAN: holo {sorted(holo_ids)} vs non-holo {sorted(plain_ids)} — "
          f"distinct products, which is what TCGdex gets wrong.")
else:
    print("INCONCLUSIVE: at least one card returned no Cardmarket product.")

print(f"\nspent {budget.used()} of {budget.limit} today; "
      f"{budget.remaining()} left.")
