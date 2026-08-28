# TomBot — Pokémon card collection tracker

Self-hosted, single-user web app to track a Pokémon card collection: which cards
you own, which you still need to complete a set, and what the collection is worth.

## Architecture

- **Flask app factory** (`tombot/__init__.py`) wiring blueprints under `tombot/api/`.
- **`PokemonRepo`** (`tombot/services/repository.py`) is the **only** place that
  writes SQL. Everything else goes through it.
- **SQLite** (`tombot/services/schema.sql`). WAL, `foreign_keys=ON`, thread-local
  connections, re-entrant `tx()`.
- **Frontend** is a small vanilla-JS SPA in `static/js/` (no build step). It is
  loaded as ES modules — validate with `node --check` on a `.mjs` copy, because
  `node --check file.js` parses as CommonJS and hides a missing brace.

## The one data source: tcggo

Catalogue, card images, Cardmarket versions **and** prices all come from **tcggo**
(CardMarket API TCG on RapidAPI). There is no other source — the old pokemontcg.io
and TCGdex adapters were removed because each mapped a card to one price for all
its printings, mispricing every reprint.

tcggo is **metered**: the plan bills per request past a daily allowance. Every
call goes through `RequestBudget` (`services/budget.py`), which counts requests in
the database over a rolling 24h window and refuses to send one past the cap
(`TCGGO_DAILY_LIMIT`, default 40). Set the key in `.env` as `TCGGO_API_KEY`.

Sets are imported **one at a time from the Mantenimiento → Sets tab**. There is no
bootstrap: a fresh install is an empty schema, and importing a set is what fills
it. Importing stores the set's cards and its Cardmarket products (with prices) in
`market_products`, and creates a collecting goal for it.

## Data model

- **`official_sets` + `cards`** — the catalogue, from a tcggo import. Card ids are
  `{setcode}-{number}` (e.g. `bs-4`). Always the whole set.
- **`market_products`** — every Cardmarket product for an imported set: one row per
  printing/version, with its price and its own Cardmarket URL. A card's versions
  are its products.
- **`collection_sets` + `set_slots` + `set_slot_cards`** — a *collecting goal*: a
  **rule** over one or more catalogue sets. A slot is one completion target,
  satisfied by owning any member card. Rules live in `collection_sets.rules_json`
  and are materialised into slots by `SetBuilder`. The rule is editable per set
  (mode: all / sin holos / solo holos / sin comunes — see `api/sets.py`), which is
  how the catalogue stays whole while what you *collect* from it changes. A slot's
  `source` is `rule` or `manual`; a rebuild leaves manual ones alone.
- **`collection_items`** — what you physically own: `(card_id, variant, condition,
  language)` unique, plus `market_product_id` (the exact Cardmarket product chosen
  in the add-card modal).
- **`price_cache`** — the resolved price per owned printing.
- **`price_modifiers`** — condition/language/variant multipliers, editable.

## Pricing

Prices are read **locally** from `market_products` by the product id on each owned
row — no per-card network call, no guessing which printing a variant is. A row
with no chosen product is left unpriced (a wrong number is worse than none).
Re-importing a set is what refreshes its prices. See `services/pricing.py`.

## Conventions

- **`schema.sql` is the single source of truth. There are no migrations.** A
  schema change is an edit to `schema.sql`; a database from before it is recreated
  (the app is rebuilt from set imports, so there is nothing to preserve). `init_db`
  just runs the schema; it is idempotent.
- **Silent fallbacks are the enemy.** Most bugs here came from a lookup that missed
  and returned something plausible (a missing multiplier → 1.00, an unknown set id
  → "modern set"). Prefer failing or warning over guessing. `services/health.py`
  (Mantenimiento → Revisión de datos) actively looks for these mismatches.
- **One local instance.** Run one server, one database; switch branches by
  checkout + restart. The tcggo key is metered per-key, so several instances
  against one key overspend it.
- **CLAUDE reviewers:** the API budget is real money past the daily cap. Do not
  make live tcggo calls casually; the version picker and pricing read from
  already-imported local data.

## Commands & run

```
flask init-db     # create the schema (idempotent). Startup runs this; no bootstrap.
flask prices      # re-price the collection from imported products (local, no network)
flask snapshot    # write a collection snapshot for the history charts
flask monthly     # prices + snapshot (what cron calls)
flask scheduler   # run monthly on a schedule, blocking (its own container)
```

Docker: `docker compose up -d`. Config is `.env` (see `.env.example`). Port maps
`8090:8080`. `pytest` runs the suite.
