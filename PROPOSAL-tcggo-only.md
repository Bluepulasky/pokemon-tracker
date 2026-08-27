# Proposal: one source, and a card that always maps to a real product

Status: **proposal, nothing committed.** Written 2026-08-27.

## What this replaces

Today a collection row records a card id plus our own invented taxonomy —
`variant` (holo / reverse / normal) and `edition` (1st edition / shadowless /
unlimited). Nothing guarantees that combination corresponds to anything a shop
actually sells. To get a price we then *resolve* it: pick a printing, pick a
source, pick which field of that printing is the right number.

Every pricing bug so far has come from that resolution layer, not from the
prices:

* the reverse-holo fields being read as "the holo price"
* `variant_key = NULL` on rows recorded before printings existed
* TCGdex giving one Cardmarket product to 199 different cards
* Gym trainers' products bleeding onto `Brock's Geodude`

## The change

**A collection row references a tcggo card, and a tcggo card is a Cardmarket
product.** No resolution step, because there is nothing left to resolve.

```
now       (card_id, variant, edition)  --resolve-->  printing  --?-->  product
proposed  (tcggo_card_id)              ==            product
```

The add-card dialog stops offering our vocabulary and offers **the versions
that exist for that card**, fetched from the API. Pick "Charizard, Base Set" and
the version list is whatever Cardmarket actually sells — `Unlimited`,
`Shadowless`, `1st Edition Shadowless` — never a combination that cannot be
priced.

What this deletes: `variant_map.py`, the printing-resolution branch of
`pricing.py`, the per-source price-field tables, and most of the reason the
shared-product guard exists.

## Why tcggo can carry this

Verified against the live API today:

```
base2-3  Flareon holo      cm 516339   49.39 EUR   411 for sale
base2-19 Flareon non-holo  cm 273816   12.24 EUR   503 for sale
```

Distinct products, correct prices. It also carries, in the same payload, things
we currently cannot get at all: the print run as a first-class field, lowest
near-mint **per country** including ES, how many copies are actually listed, and
eBay sold medians by grade.

## What is not proven, and must be before this is built

**1. Coverage.** Filtering `name=Charizard, card_number=4` returns 7 records
across all sets and only 2 from Base Set: `Shadowless` and `1st Edition
Shadowless`. The plain Unlimited Base Set Charizard — the common one — is not
among them. Either it is missing, or its `card_number` is null and the filter
skips it. We already know `tcgid` is null on some records, so sparse fields are
a real pattern here, not a guess.

If coverage is genuinely incomplete, this proposal fails: a card the user owns
and cannot select is worse than a card priced by a wobbly heuristic.

**2. Migration.** Existing rows carry our taxonomy. They would need matching to
tcggo records once, by set, number and version, with anything ambiguous left for
the user to resolve rather than guessed.

**3. Single supplier.** One metered API becomes the only way to price anything.
At 100 requests a day, a full catalog refresh has to be paced, and if the plan
changes or the service stops, there is no fallback. Keeping pokemontcg.io for
the *catalog* — names, numbers, images — costs nothing and removes that risk;
only pricing and version identity would come from tcggo.

## Verification before building

One expansion, fetched by id and paged through — roughly 5 to 10 requests
against a daily allowance of 80.

It answers: does every card in Base Set appear, does every card carry a version,
does every version carry its own Cardmarket product, and how many cards come
back per request. That last number decides whether a full catalog import is a
one-day job or a one-week job.

Cheap, and it is the difference between proposing this and knowing it works.
