# TOMBOT POKEMON TRACKER — Implementation Plan

> Working plan derived from `TOMBOT POKEMON TRACKER.pdf` (the original spec).
> This document **supersedes** the PDF where the two disagree. Every deviation is
> listed in §2 with the reason.
>
> Status: v0 skeleton committed. Roadmap in §9.

---

## 1. What this application is

A single-user, self-hosted web app to manage a physical Pokémon card collection.

Four concepts, deliberately kept separate (this is the spine of the whole design and
the spec is right to insist on it):

| Concept | Answers | Owned by |
|---|---|---|
| **Catalog** | *Which cards exist?* | External source, overwritable |
| **Personal set** | *Which cards do I consider part of "my Base Set"?* | User, never overwritten |
| **Collection** | *Which physical cards do I own?* | User, never overwritten |
| **Price** | *What is a card roughly worth?* | External source, cached |

A refresh of the catalog must never destroy the other three.

---

## 2. Review of the original spec — corrections and gaps

The spec is coherent and the domain separation is well judged. The problems below are
things that would have caused rework or wrong numbers if built as written. Each has a
decision attached.

### 2.1 🔴 BLOCKER — `set_cards` cannot express "group reprints as one logical card"

The spec asks for two things that conflict:

- §2: *"Agrupar reprints como una misma carta lógica"* / *"Ignorar determinadas variantes"*
- §24: `set_cards(set_id, card_id, order)`

With one row per `(set, card)`, owning **both** the Base Set Charizard and the Base Set 2
Charizard counts as **two** completed entries out of a 102-card target. Completion goes
above 100% and "cartas faltantes" lies. §17 explicitly says this must count once.

**Decision — slot model.** A personal set is an ordered list of **slots**. A slot is
satisfied by owning **any one** of the catalog cards mapped to it.

```
collection_sets ──< set_slots ──< set_slot_cards >── cards
                     (position,      (many catalog cards
                      label)          satisfy one slot)
```

- Completion = `slots with >=1 owned member / total slots`.
- The normal case is 1 slot ↔ 1 card, so this costs nothing in the simple case.
- It is the *only* structure that makes "Base Set #4 = Charizard, however I got it" true.

Consequence: `set_cards` from the spec is dropped and replaced by `set_slots` +
`set_slot_cards`. Everything downstream (progress, missing list, dashboard) reads slots.

### 2.2 🔴 BLOCKER — Cardmarket has no usable public API

§10 names Cardmarket as the preferred price source. Cardmarket's API is OAuth1,
application-gated, and not granted for personal projects. Building against it would
stall the whole pricing half of the app.

**Decision — use `api.pokemontcg.io` v2 as both catalog *and* price source.** Verified
live while writing this plan:

```json
"cardmarket": {
  "url": "https://prices.pokemontcg.io/cardmarket/base1-4",
  "updatedAt": "2026/07/01",
  "prices": { "averageSellPrice": 1531.0, "lowPrice": 799.0, "trendPrice": 4184.6,
              "avg1": 14950.0, "avg7": 3939.88, "avg30": 2427.79,
              "reverseHoloTrend": 0.0, "lowPriceExPlus": 1750.0, ... }
}
```

That is **Cardmarket data, in EUR, per card, with no Cardmarket account**. It also ships
TCGplayer USD prices in the same payload, and the catalog fields (name, number, rarity,
artist, images) — one source covers §1, §10, §11 and §12.

Notes that matter:
- Upstream refreshes Cardmarket roughly monthly (`updatedAt: 2026/07/01` on 2026-08-25).
  The spec's "fetch once a month with a cron" (§12) matches the upstream cadence exactly.
  Polling more often buys nothing.
- **The API is flaky.** During research it returned HTTP 500 on maybe a third of calls,
  including on `/v2/cards/{id}`. The import and price jobs must be *resumable, retrying,
  and never on the request path of a page load.* This is a hard design constraint, not a
  nicety.
- Get the free API key (`X-Api-Key`): 20,000 req/day with, 1,000/day without.
- `TCGdex` is kept as a second adapter behind the same interface — it has **Spanish card
  names**, which matters because the user records a language per card (§8).

Default price basis: `cardmarket.prices.averageSellPrice`, falling back to `trendPrice`
then `avg30`. `trendPrice` alone is too spiky — note `trendPrice` €4184 vs
`averageSellPrice` €1531 vs `avg30` €2427 on the sample above. Basis is configurable.

### 2.3 🟠 `cards.set_id` is ambiguous

§24 gives `cards.set_id → "Set lógico principal"` while `sets` is the *personal* sets
table. One column pointing at two different concepts.

**Decision.** Add an explicit `official_sets` table. `cards.official_set_id → official_sets.id`.
Personal sets live in `collection_sets`. No overlap, no ambiguity.

### 2.4 🟠 One photo per collection row contradicts §6

§24 has `collection.image str` (one photo). §6 asks to store one photo **per variant**,
show *"la foto en mejor estado"* in the grid, and swipe through all photos in the modal.

**Decision.** Separate `collection_photos` table, N per item, with `is_primary` and
`position`. The grid picks: primary photo of the best-condition item for that card, else
catalog image, else placeholder.

### 2.5 🟠 Collection rows have no uniqueness rule → silent double counting

Nothing in the spec stops two rows of `(Charizard, Holo, NM, Español)` with quantity 1
each existing alongside a third with quantity 2. Physical counts and value would drift.

**Decision.** `UNIQUE(card_id, variant, condition, language)`. Adding an existing
combination increments `quantity` instead of inserting. Different condition = different row,
which is also what you want for valuation.

### 2.6 🟠 History cannot be derived from current state

§29 says historical collection evolution *"puede derivarse de snapshots periódicos y/o del
historial de precios"*. Price history alone cannot tell you how many cards you owned in
March. There is no record of when an item was added.

**Decision.** Two mechanisms: `created_at`/`updated_at` on collection items **plus** a
`collection_snapshots` table written by the same scheduled job that refreshes prices. Cheap
(one row a month) and it makes every §29 chart answerable.

### 2.7 🟠 "No authentication" + "deploy on a server" is an open write API

§31 says no auth is required. That is fine on `localhost`. The moment this is on a server
with a public port, anyone can `DELETE /api/collection/<id>`.

**Decision.** Keep the app auth-free internally, but:
- default bind is `127.0.0.1`, not `0.0.0.0`;
- optional `APP_TOKEN` env var → if set, every `/api/*` request needs
  `X-App-Token` (or a cookie set once from a `?token=` link). Unset = current behaviour.
- deployment doc recommends reverse proxy + basic auth or a Tailscale/WireGuard address.

Cost: ~30 lines. It stays out of the way when unused.

### 2.8 🟠 iPhone photo upload will fail as specified

§9 wants camera upload from mobile as a priority path. Not addressed:
- iOS Safari uploads **HEIC** by default. `<img>` cannot render it; Pillow cannot open it
  without `pillow-heif`. Photos would upload and then not display.
- Modern phone photos are 4–12 MB. Flask's default has no upload cap → memory blowups.
- EXIF orientation → sideways photos.
- No thumbnails → a 1,000-card grid pulls hundreds of MB on mobile.

**Decision.** Upload pipeline: reject non-image MIME → cap at `MAX_UPLOAD_MB` (default 25)
→ decode with `pillow-heif` registered → apply `ImageOps.exif_transpose` → re-encode to
JPEG q85 max 1600px long edge → generate 400px thumbnail → store with a UUID filename.
`<input type="file" accept="image/*" capture="environment">` for the camera path.

### 2.9 🟡 SQLite defaults will bite

Not mentioned in the spec, all three are real:
- `PRAGMA foreign_keys` is **OFF** by default in SQLite → every FK in §24 would be
  decorative and orphan rows would accumulate.
- No WAL → the price job writing blocks page reads.
- No `busy_timeout` → `database is locked` under the scheduler.

**Decision.** Every connection opens with `foreign_keys=ON`, `journal_mode=WAL`,
`busy_timeout=5000`, `synchronous=NORMAL`. Centralised in `PokemonRepo`.

### 2.10 🟡 "sin holos" / "sin comunes" has no mechanism

The set list in §2 is written as prose rules — *Jungle (sin holos)*, *EX Team Rocket Returns
(sin comunes)* — but §24 only stores an explicit card list. Somebody would have to hand-curate
~1,100 rows, and a catalog refresh would silently drop new cards.

**Decision.** `collection_sets.rules_json` holds a small declarative rule, and slots are
**materialised** from it by a rebuild command. Rarities were verified against the live API and
map cleanly:

```
base2 (Jungle)  →  Common:16  Uncommon:16  Rare:16  Rare Holo:16
```

so *"sin holos"* is exactly `exclude_rarities: ["Rare Holo"]`, and *"sin comunes"* is
`exclude_rarities: ["Common"]`. Rule shape:

```json
{ "include_sets": ["base2"],
  "exclude_rarities": ["Rare Holo"],
  "exclude_cards": [], "include_cards": [],
  "merge": [ { "label": "Charizard", "cards": ["base1-4", "base4-4"] } ] }
```

Rebuild is **non-destructive**: slots with `source='manual'` and manual member edits survive.
Only `source='rule'` slots are recomputed.

### 2.11 🟡 Verified set IDs for the requested collection

Checked against the live API so the seed does not guess:

| Personal set | Source set | id | Cards | Rule |
|---|---|---|---|---|
| Base Set | Base | `base1` | 102 | all |
| Jungle (sin holos) | Jungle | `base2` | 64 | −16 Rare Holo → 48 |
| Fossil (sin holos) | Fossil | `base3` | 62 | −15 Rare Holo → 47 |
| Team Rocket (sin holos) | Team Rocket | `base5` | 83 | −17 Rare Holo → 66 |
| Gym Heroes (sin holos) | Gym Heroes | `gym1` | 132 | −19 Rare Holo → 113 |
| Gym Challenge (sin holos) | Gym Challenge | `gym2` | 132 | −20 Rare Holo → 112 |
| WOTC Promos | Wizards Black Star Promos | `basep` | 53 | all |
| Neo Genesis (sin holos) | Neo Genesis | `neo1` | 111 | − Rare Holo |
| Neo Discovery (sin holos) | Neo Discovery | `neo2` | 75 | − Rare Holo |
| Neo Revelation (sin holos) | Neo Revelation | `neo3` | 66 | − Rare Holo |
| Neo Destiny (sin holos) | Neo Destiny | `neo4` | 113 | − Rare Holo |
| EX Team Rocket Returns (sin comunes) | Team Rocket Returns | `ex7` | 111 | − Common |

Groups: **Gen1** (base1…basep), **Gen 2** (neo1…neo4), **Gen 3** (ex7).

Two judgement calls flagged for the maintainer to confirm:
- `base5` Team Rocket includes 1 `Rare Secret` (#83 Dark Raichu). Kept — it is not a holo
  rare in the "sin holos" sense. Easy to exclude via `exclude_cards`.
- Base Set: `base4` (Base Set 2) is **not** its own personal set. If the user owns Base Set 2
  cards that stand in for Base Set slots, add them as `merge` members rather than a new set.

Total catalog to import: **~1,100 cards** across 12 sets. Small — a full import is a couple of
minutes and fits comfortably in SQLite. **Do not import the full 20,000-card catalog**; the
spec's `/api/cards` with no pagination would choke on it.

### 2.12 🟡 Price lookup is per *printing*, not per condition/language

§14 wants price to account for card + variant + condition + language. No public source prices
by condition or by Spanish/Portuguese printing. Pretending otherwise gives false precision.

**Decision.** Price = `base_price(card, variant) × condition_multiplier × language_multiplier`,
both multipliers stored in a `price_modifiers` table and editable. Defaults (documented as
*estimates*, per §31):

```
NM 1.00 · LP 0.85 · MP 0.70 · HP 0.50 · Damaged 0.35
en 1.00 · es 0.90 · pt 0.85 · other 0.85
```

Fallback chain, matching §14's intent:
`exact (card, variant)` → `card, any variant` → `unpriced` (shown as "—", never as €0).

Distinguishing "worth zero" from "no data" is important — otherwise the dashboard total is
quietly wrong and nobody can tell.

### 2.13 🟡 Cron inside Docker

§30 wants a scheduled job. Running `cron` inside the app container means a second process,
no logs in `docker logs`, and silent failures.

**Decision.** Ship it as a CLI command (`flask prices refresh`, `flask snapshot`) plus a
`SCHEDULER_ENABLED` flag using APScheduler in-process for the simple case. Host cron or a
systemd timer calling `docker compose exec` is documented as the robust option. Either way
the job is the *same* code path and is manually runnable, which matters when the upstream API
is throwing 500s.

### 2.14 🟡 Catalog images should be cached locally

The spec stores photos on the filesystem but says nothing about the ~1,100 catalog images. Hot
linking `images.pokemontcg.io` for every grid tile means a slow, offline-fragile grid.

**Decision.** Import downloads the `small` image to `media/catalog/<card_id>.png` in the
background, with the remote URL kept as fallback. ~40 MB for the whole target catalog.

### 2.15 API additions

Missing from §23 and needed: `GET /api/collection/<id>`, slot/set-membership editing,
`GET /api/sets/<id>/missing`, `GET /api/search`, `GET /api/stats/history`, `GET /api/healthz`,
pagination (`page`, `page_size`) on every list endpoint, and a documented error envelope
(`{"error": {"code", "message"}}`). Full surface in §6.

### 2.16 Smaller notes

- No `created_at`/`updated_at` anywhere in §24 → added everywhere.
- `cards.number` is a **string** (`"4"`, `"H12"`, `"SH1"`). Sorting by it lexically puts #10
  before #2. Added a derived `number_sort` numeric column.
- Currency is stored per price row. Everything is displayed in EUR; USD sources need an FX
  rate, so TCGplayer is import-only for now and not mixed into totals.
- §5 placeholder ("Base Set #4", grey card, dark text) is a **CSS/SVG placeholder**, not a
  generated image file.

---

## 3. Data model (corrected)

```
official_sets ──< cards ──< set_slot_cards >── set_slots >── collection_sets
                    │
                    ├──< collection_items ──< collection_photos
                    ├──< price_cache
                    └──< price_history

collection_snapshots        price_modifiers        app_meta
```

Full DDL: `app/services/schema.sql`. Table-by-table notes:

| Table | Purpose | Key constraint |
|---|---|---|
| `official_sets` | Real-world sets from the source | PK `id` (`base1`) |
| `cards` | Normalised catalog. Overwritable. | PK `id` (`base1-4`) |
| `collection_sets` | User's personal sets | `rules_json`, `group_name`, `position` |
| `set_slots` | One completion target | `(set_id, position)`, `source` |
| `set_slot_cards` | Catalog cards satisfying a slot | `UNIQUE(set_id, card_id)` via index |
| `collection_items` | Physical inventory | `UNIQUE(card_id, variant, condition, language)` |
| `collection_photos` | User photos, N per item | `is_primary`, cascade delete |
| `price_cache` | Current known price | PK `(card_id, variant, source)` |
| `price_history` | Monthly snapshots | `UNIQUE(card_id, variant, source, captured_on)` |
| `collection_snapshots` | Collection-level time series | one row per run |
| `price_modifiers` | Condition/language multipliers | PK `(kind, key)` |
| `app_meta` | `schema_version`, job timestamps | PK `key` |

### Completion query (the one that has to be right)

```sql
SELECT s.id, s.name,
       COUNT(DISTINCT sl.id) AS target,
       COUNT(DISTINCT CASE WHEN ci.id IS NOT NULL THEN sl.id END) AS owned
FROM collection_sets s
JOIN set_slots sl        ON sl.set_id = s.id
JOIN set_slot_cards ssc  ON ssc.slot_id = sl.id
LEFT JOIN collection_items ci ON ci.card_id = ssc.card_id
GROUP BY s.id;
```

`COUNT(DISTINCT sl.id)` on the owned side is what makes Charizard-holo + Charizard-non-holo
count once, satisfying §17.

---

## 4. Architecture

```
Browser (Vanilla JS SPA)
        │  fetch /api/*
Flask blueprints  (app/api/*.py)     ← no SQL here, ever
        │
PokemonRepo       (app/services/repository.py)   ← the only place that touches SQLite
        │
SQLite (WAL)  +  media/ on filesystem
        ▲
PriceService / CatalogImporter / SetBuilder      ← call the repo, never sqlite3
```

`PokemonRepo` is the hard rule from §22 and §31. Route handlers get dicts, not cursors.

Layout:

```
tombot-pokemon-tracker/
├── app.py                  # entrypoint / app factory wiring
├── app/
│   ├── config.py           # env-driven config
│   ├── api/                # routes: catalog, sets, collection, images, prices, stats
│   ├── services/
│   │   ├── repository.py   # PokemonRepo — ALL SQL
│   │   ├── schema.sql
│   │   ├── sources/        # pokemontcgio.py, tcgdex.py (same interface)
│   │   ├── importer.py     # catalog import, resumable
│   │   ├── setbuilder.py   # rules_json -> slots
│   │   ├── pricing.py      # fallback chain + modifiers
│   │   └── images.py       # HEIC/EXIF/resize/thumbs
│   └── cli/                # flask commands: init-db, import, seed-sets, prices, snapshot
├── static/  templates/     # SPA
├── data/pokemon.db         # gitignored
└── media/{catalog,collection,thumbs}/   # gitignored
```

---

## 5. Frontend

Vanilla JS SPA, hash routing, four views per §26: **Dashboard · Sets · Collection · Missing**.

Non-obvious requirements that came out of the review:

- **Lazy loading is mandatory.** A 132-card Gym Heroes grid on mobile = 132 images.
  `loading="lazy"` + `IntersectionObserver` for the fetch-on-scroll case.
- **Missing cards are placeholders, not images** — CSS card with `#4` and the set code, grey
  fill, per §5's sketch. Zero network cost for the 40% of a grid you do not own.
- **The modal is the app.** Per §28 it carries catalog info, all variants of that card as a
  horizontally swipeable strip (§6), add/edit/delete, photo upload, and price breakdown.
- Filters (§4): set, condition, variant, language, rarity, owned/missing, plus sort.
  Kept in the URL hash so a filtered view is linkable and survives reload.
- Unique vs physical counts shown side by side everywhere (§4): *"67 cartas · 94 físicas"*.

---

## 6. API surface

Error envelope: `{"error": {"code": "not_found", "message": "..."}}`. Lists paginate with
`?page=&page_size=` and return `{"data": [...], "page", "page_size", "total"}`.

**Catalog**
```
GET    /api/cards                 ?q= &set= &rarity= &page=
GET    /api/cards/<id>
POST   /api/catalog/import        { "sets": ["base1", ...] }   → job result
```
**Personal sets**
```
GET    /api/sets                                  list + progress
GET    /api/sets/<id>                             slots + owned state  (the set grid view)
POST   /api/sets           PUT /api/sets/<id>     DELETE /api/sets/<id>
POST   /api/sets/<id>/rebuild                     re-materialise from rules_json
GET    /api/sets/<id>/missing                     ?sort=number|name|rarity|value
POST   /api/sets/<id>/slots        PUT/DELETE /api/sets/<id>/slots/<slot_id>
```
**Collection**
```
GET    /api/collection            ?set= &condition= &variant= &language= &rarity= &q= &sort=
GET    /api/collection/<id>
POST   /api/collection            upsert on (card_id,variant,condition,language)
PUT    /api/collection/<id>       DELETE /api/collection/<id>
GET    /api/collection/by-card/<card_id>          all variants — powers the modal
```
**Images**
```
POST   /api/collection/<id>/photos          multipart, returns photo record
DELETE /api/collection/photos/<photo_id>
PUT    /api/collection/photos/<photo_id>    { "is_primary": true }
GET    /media/...                           served by Flask in dev, by nginx in prod
```
**Prices**
```
GET    /api/prices/<card_id>       cached price + age + all variants
POST   /api/prices/refresh         { "stale_days": 25 }   → refreshes collection cards only
GET    /api/prices/history         ?card_id= | ?set_id= | (whole collection)
```
**Stats**
```
GET    /api/dashboard              §16 in one payload
GET    /api/stats/history          §29 time series from collection_snapshots
GET    /api/search?q=              §19 global, catalog + collection
GET    /api/healthz
```

---

## 7. Scheduled work (§30)

```
monthly job
  ├─ select DISTINCT card_id, variant FROM collection_items      (collection only, §30)
  ├─ skip anything whose price_cache.updated_at < stale_days old
  ├─ fetch in batches of 250 via q=id:a OR id:b ...              (not one call per card)
  ├─ retry 5× with exponential backoff — upstream 500s are routine
  ├─ upsert price_cache, append price_history (one row per day max)
  └─ write collection_snapshots
```

Batching matters: 800 owned cards is **4 API calls**, not 800. §11's "one lookup per card,
multiply by quantity" is satisfied a fortiori.

---

## 8. Deployment & handover

The repo is handed over as a **git bundle** — a single file containing the full history that
the maintainer clones and pushes to his own remote:

```bash
./scripts/make-bundle.sh                 # → dist/tombot-pokemon-tracker.bundle
# maintainer:
git clone tombot-pokemon-tracker.bundle tombot-pokemon-tracker
git remote set-url origin git@github.com:<him>/<repo>.git && git push -u origin main
```

Better than a zip: one file, real history, verifiable, and Syncthing-friendly. See `HANDOVER.md`.

Runtime: `docker compose up -d`, with `data/` and `media/` as bind-mounted volumes so a
container rebuild never touches the database or the photos.

---

## 9. Roadmap

| Phase | Scope | State |
|---|---|---|
| **0** | Repo, schema, `PokemonRepo`, config, Docker, handover tooling | ✅ committed |
| **1** | Catalog import from pokemontcg.io + local image cache | ✅ committed |
| **2** | Set seeding from rules → slots; completion query | ✅ committed |
| **3** | Collection CRUD API + upsert semantics | ✅ committed |
| **4** | SPA: sets grid, set detail, card modal, collection view | 🔨 in progress |
| **5** | Photo upload pipeline (HEIC, EXIF, thumbs) | ⬜ |
| **6** | Pricing: fetch, cache, modifiers, fallback chain | ⬜ |
| **7** | Dashboard + missing/wishlist views | ⬜ |
| **8** | Snapshots, history charts, scheduler | ⬜ |
| **9** | Polish: mobile pass, empty states, optional `APP_TOKEN` | ⬜ |

## 10. Explicitly out of scope

Per §9/§28: no OCR, no card recognition. Per §31: single user, no accounts, no sharing,
no marketplace integration, no trading, no deck building. Prices are estimates and are
labelled as such in the UI.

## 11. Open questions for the maintainer

1. Base Set 2 (`base4`) — separate personal set, or `merge` members of Base Set slots?
2. Team Rocket `Rare Secret` #83 Dark Raichu — in or out of "sin holos"?
3. WOTC Promos (`basep`, 53 cards) — all of them, or a subset?
4. Is the box reachable from the public internet? Decides whether `APP_TOKEN` ships on.
