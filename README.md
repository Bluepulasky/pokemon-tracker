# TomBot Pokémon Tracker

Self-hosted, single-user web app for managing a physical Pokémon card collection:
personal set definitions, completion tracking, own photos, and estimated value from
Cardmarket prices.

Built from the spec in `TOMBOT POKEMON TRACKER.pdf`. **`PLAN.md` is the authoritative
document** — it records the corrections made to that spec and why.

```
Flask + Vanilla JS SPA · SQLite (WAL) · photos on the filesystem · Docker
```

## Quick start

```bash
make install       # venv + dependencies
make bootstrap     # schema + catalog import (~1,100 cards) + 12 personal sets
make run           # http://127.0.0.1:8080
```

Or with Docker:

```bash
cp .env.example .env      # optional: add a free pokemontcg.io API key
docker compose up -d --build
docker compose exec app flask bootstrap
```

`bootstrap` is idempotent. The upstream API returns HTTP 500 fairly often, so if a set
fails, just run it again — completed sets are skipped, nothing is lost.

## What it does

| Feature | Where |
|---|---|
| Personal sets defined by rules (`Jungle (sin holos)`) | `tombot/services/seed_sets.py` |
| Set grid with placeholders for missing cards | `#/set/<id>` |
| Collection inventory with filters | `#/collection` |
| Card modal: variants, photos, prices, edit | `static/js/modal.js` |
| Missing-cards wishlist | `#/missing` |
| Dashboard + value history | `#/dashboard` |
| Monthly price refresh | `flask monthly` |

## Concepts

Four things are kept deliberately separate. This is the design's spine:

- **Catalog** — which cards exist. Comes from an external source, safe to overwrite.
- **Personal set** — which cards *you* consider part of "your Base Set". Yours.
- **Collection** — which physical cards you actually own. Yours.
- **Price** — roughly what a card is worth. External, cached.

Re-importing the catalog never touches the last three.

### Slots, not cards

A personal set is a list of **slots**. A slot is completed by owning **any one** of the
catalog cards mapped to it. That is what makes a holo and a non-holo Charizard count as
one completed card while still being two physical cards and two separate values.

```
collection_sets ──< set_slots ──< set_slot_cards >── cards
```

### Set rules

Personal sets are materialised from a declarative rule, so a catalog refresh does not
mean re-curating a thousand rows:

```json
{ "include_sets": ["base2"], "exclude_rarities": ["Rare Holo"] }
```

Rebuild with `POST /api/sets/<id>/rebuild` or `flask seed-sets`. Slots you edited by
hand (`source='manual'`) survive a rebuild.

## Prices

Cardmarket's own API is application-gated and not obtainable for a personal project.
`api.pokemontcg.io` republishes Cardmarket EUR prices per card with no account, and is
used as both catalog and price source. See `PLAN.md` §2.2.

No public source prices by *condition* or by *printing language*, so:

```
estimate = base_price(card, variant) × condition_multiplier × language_multiplier
```

Multipliers live in the `price_modifiers` table and are editable. Cards with no price
data show `—`, never `€0`, so a low total reads as missing data rather than a cheap
collection.

Refresh monthly — that matches how often upstream updates Cardmarket data:

```cron
0 4 1 * *  cd /srv/tombot && docker compose exec -T app flask monthly
```

## Commands

```bash
flask init-db                        # schema + default modifiers
flask import-catalog [--sets a,b]    # catalog import, resumable
flask seed-sets [--rebuild]          # personal sets from seed_sets.py
flask prices [--all]                 # refresh prices for owned cards
flask snapshot                       # collection snapshot for history charts
flask monthly                        # prices + snapshot (cron target)
flask bootstrap                      # all of the above, fresh install
```

## Configuration

All via environment variables — see `.env.example` and `tombot/config.py`.

Notable: `APP_TOKEN`. The app has no login by design (single user). It binds to
`127.0.0.1` by default. If you expose it beyond your LAN, set `APP_TOKEN` and every
`/api/*` call will require an `X-App-Token` header.

## Layout

```
app.py                      entrypoint
tombot/
  config.py                 env config + domain vocabularies
  api/                      Flask blueprints — no SQL here
  services/
    repository.py           PokemonRepo — the only module that touches SQLite
    schema.sql
    sources/                pokemontcgio adapter (TCGdex slot open)
    importer.py setbuilder.py pricing.py images.py seed_sets.py
  cli/                      flask commands
static/ templates/          Vanilla JS SPA
data/pokemon.db             gitignored
media/{catalog,collection,thumbs}/   gitignored
tests/
```

`PokemonRepo` is a hard rule: route handlers get dicts, never cursors.

## Tests

```bash
make test
```

The suite covers the completion semantics that are easy to get wrong — variant
collapsing, quantity vs completion, the unique constraint that stops double counting,
and that foreign keys are actually enforced.

## Handover

See `HANDOVER.md`. Short version: `make bundle` produces a single file containing the
full git history that the new maintainer clones and pushes to his own remote.

## Not in scope

No OCR or card recognition (spec §9/§28). No accounts, no trading, no deck building.
Prices are estimates and are labelled as such.
