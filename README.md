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

### On a home server (Docker)

```bash
cp .env.example .env
$EDITOR .env                 # set APP_PORT, BIND_ADDR, PUID/PGID
docker compose up -d
```

That is the whole install. The container creates the schema, imports the catalog
(~1,100 cards), builds the personal sets and resolves the Cardmarket links on first
start, then serves. Watch it with `make docker-logs`.

The upstream API returns HTTP 500 fairly often. Everything the bootstrap does is
idempotent and resumable, so a failed set is picked up on the next restart — nothing
is lost and nothing is duplicated.

**Changing the port** — one value in `.env`, nothing else:

```ini
APP_PORT=9090
```

**Reaching it from other machines on your LAN:**

```ini
BIND_ADDR=0.0.0.0
APP_TOKEN=<openssl rand -hex 24>
```

`BIND_ADDR` defaults to `127.0.0.1` deliberately. The API has no login, so anything that
can reach the port can delete your collection — set `APP_TOKEN` before opening it up. The
browser needs it once: `localStorage.setItem('app_token', '<value>')`.

**File ownership** — set `PUID`/`PGID` to your own `id -u` / `id -g`, otherwise the
database and photos end up owned by root on the host.

Two containers come up: `app` (the web UI) and `scheduler` (the monthly price refresh).
Skip the scheduler with `make docker-app` and use host cron instead if you prefer.

### Running flask commands in the container

**You normally do not need to.** The container runs `init-db`, `import-catalog`,
`seed-sets` and `resolve-links` itself on first start — `docker compose up -d` is the
whole setup. Watch it happen with `make docker-logs`.

Run them by hand when you want to retry something that failed, rebuild the sets after
editing the rules, or refresh prices off-schedule:

```bash
make docker-bootstrap   # schema + catalog + sets + links, all idempotent
make docker-initdb      # schema only
make docker-sets        # rebuild personal sets from seed_sets.py
make docker-links       # resolve Cardmarket product URLs
make docker-prices      # refresh prices
make docker-shell       # a shell, for anything else
```

Every one of those is safe to re-run. `import-catalog` skips sets it already has,
`seed-sets` preserves hand-edited slots, and none of them touch your collection.

**If you are not using make**, pass the user explicitly. `docker compose exec` bypasses
the entrypoint and runs as root, which leaves root-owned WAL files beside the database:

```bash
docker compose exec --user $(id -u):$(id -g) app flask seed-sets   # correct
docker compose run  --rm app flask seed-sets                       # also correct
docker compose exec app flask seed-sets                            # runs as root — avoid
```

### Trying the UI before you own anything

A fresh install has a full catalog and 919 empty set slots, which is correct but hard to
judge. To fill the collection with sample cards:

```bash
make docker-demo         # ~180 records across 10 sets, deterministic
make docker-demo-clear   # remove them again
```

`docker-demo-clear` deletes **all** collection items and photos, so do not run it once
you have entered real cards. Neither command touches the catalog or the personal sets.

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

Every card links out to its Cardmarket product page from the modal. Those URLs are
resolved once (`flask resolve-links`) and stored, because the slug is Cardmarket-internal
and not derivable — `Charizard-V2-BS4`, `Brocks-Rhydon-GH2`. Set `CARDMARKET_LOCALE`
(default `es`) to pick the site language.

Refresh monthly — that matches how often upstream updates Cardmarket data. The
`scheduler` container does this for you (`SCHEDULER_CRON_DAY` / `SCHEDULER_CRON_HOUR`
in `.env`). If you would rather use host cron, run `make docker-app` to skip that
container and add:

```cron
0 4 1 * *  cd /srv/tombot-pokemon-tracker && docker compose exec -T app flask monthly
```

The scheduler runs as its own container on purpose: an in-process scheduler inside
gunicorn fires once per worker, so every price run would happen `WEB_CONCURRENCY` times.

## Commands

```bash
flask init-db                        # schema + default modifiers
flask import-catalog [--sets a,b]    # catalog import, resumable
flask seed-sets [--rebuild]          # personal sets from seed_sets.py
flask resolve-links                  # Cardmarket product URLs, resumable
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
