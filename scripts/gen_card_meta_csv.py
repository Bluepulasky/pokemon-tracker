"""Regenerate the pre-baked card-metadata fix file.

Two inputs, both offline:

* The tcggo response cache, for the illustrator and the supertype. tcggo returns
  both on every card record, but imports that ran before those columns existed
  never stored them.
* A local copy of the pokemon-tcg-data set files (`cards/en/<set>.json` from
  https://github.com/PokemonTCG/pokemon-tcg-data), for the energy type / colour
  (Fire, Water, …). tcggo has no such field at all — not on the bulk search, not
  on the card detail — so this is the only way the Color filter gets its data.
  It is a build-time input for this script only: the app itself never reads
  pokemontcg.io, and the file is joined to our cards by set + number and then
  checked by name, so a card whose name disagrees gets no type rather than a
  wrong one.

Writes tombot/data/card_meta.csv — a card_id -> {supertype, types, artist} table
shipped with the app so any install can fill the gaps offline (see
`flask fix-card-meta` / Mantenimiento), with no re-import and no API cost.

Run from the repo root:
    PYTHONPATH=. .venv/bin/python scripts/gen_card_meta_csv.py [--ptcg-dir DIR] [--db data/pokemon.db]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sqlite3
from pathlib import Path

from tombot.services.card_meta import join_list
from tombot.services.tcggo_catalog import (card_id_for, resolve_collisions,
                                           split_code)

OUT = Path("tombot/data/card_meta.csv")
CACHE_GLOBS = [".cache/**/*.json", "data/.cache-tcggo/*.json"]

# Our set code -> the pokemon-tcg-data set id(s) holding the same cards. tcggo
# confirms these itself: its `tcgid` on a card is "<ptcg set>-<number>". One
# tcggo episode can span two ptcg sets (Celebrations bundles the Classic
# Collection), so a code may list several; a card is looked up in each, in
# order, and the name check decides.
PTCG_SETS = {
    "BS": ["base1"], "JU": ["base2"], "FO": ["base3"], "TR": ["base5"],
    "GH": ["gym1"], "GC": ["gym2"], "NG": ["neo1"], "ND": ["neo2"], "NR": ["neo3"],
    "LC": ["base6"], "HS": ["hgss1"], "EVO": ["xy12"], "CEL": ["cel25", "cel25c"],
}


def _artist(a):
    if isinstance(a, dict):
        return a.get("name") or a.get("slug") or ""
    return a or ""


def _norm(name: str) -> str:
    """Names for comparison: case, accents-as-typed, punctuation and spacing
    differences between the two catalogues must not count as a mismatch."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower().replace("é", "e"))


def _records():
    for pattern in CACHE_GLOBS:
        for f in glob.glob(pattern, recursive=True):
            try:
                d = json.load(open(f))
            except (OSError, ValueError):
                continue
            if isinstance(d.get("body"), str):
                try:
                    d = json.loads(d["body"])
                except ValueError:
                    continue
            data = d.get("data") if isinstance(d, dict) else None
            if isinstance(data, list):
                yield from (c for c in data
                            if isinstance(c, dict) and c.get("card_code_number"))


def _cache_rows() -> dict[str, dict]:
    """card_id -> {name, set, number, supertype, artist} from the tcggo cache."""
    # Build product rows and run the same collision resolution the importer does,
    # so the CSV's card_ids match what an import produces (e.g. cel-2-blastoise).
    products = []
    for c in _records():
        prefix, number = split_code(c.get("card_code_number") or "")
        cid = card_id_for(prefix, number)
        if not cid or cid.endswith("-") or not c.get("cardmarket_id"):
            continue
        products.append({
            "product_id": c["cardmarket_id"], "card_id": cid,
            "name": c.get("name") or "", "set": prefix.upper(), "number": number,
            "artist": _artist(c.get("artist")), "supertype": c.get("supertype") or "",
        })
    resolve_collisions(products)

    rows: dict[str, dict] = {}
    for p in products:
        cur = rows.get(p["card_id"])
        if cur is None:
            rows[p["card_id"]] = {k: p[k] for k in
                                  ("card_id", "name", "set", "number", "supertype", "artist")}
        else:                                   # fill any blank a sibling left
            cur["artist"] = cur["artist"] or p["artist"]
            cur["supertype"] = cur["supertype"] or p["supertype"]
    return rows


def _db_rows(db: Path) -> dict[str, dict]:
    """card_id -> {name, set, number} from an imported database, for sets the
    cache no longer holds (a re-imported set drops out of the cache; the DB
    still has its cards). Carries no artist/supertype: those come from tcggo."""
    if not db.exists():
        return {}
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return {r["id"]: {"card_id": r["id"], "name": r["name"],
                          "set": (r["ptcgo_code"] or r["official_set_id"]).upper(),
                          "number": r["number"], "supertype": "", "artist": ""}
                for r in con.execute(
                    "SELECT c.id, c.name, c.number, c.official_set_id, s.ptcgo_code "
                    "FROM cards c JOIN official_sets s ON s.id = c.official_set_id")}
    finally:
        con.close()


def _ptcg_index(ptcg_dir: Path) -> dict[str, dict[str, list[dict]]]:
    """ptcg set id -> number -> [cards]. A number can repeat (cel25c "15")."""
    index: dict[str, dict[str, list[dict]]] = {}
    for sets in PTCG_SETS.values():
        for sid in sets:
            path = ptcg_dir / f"{sid}.json"
            if not path.exists():
                print(f"  (no {path}: {sid} gets no types)")
                continue
            by_number: dict[str, list[dict]] = {}
            for c in json.load(path.open()):
                by_number.setdefault(str(c.get("number") or "").lower(), []).append(c)
            index[sid] = by_number
    return index


def _types_for(row: dict, index) -> list[str] | None:
    """The energy types of our card, or None when no ptcg card of the same
    number carries the same name (nothing is guessed)."""
    for sid in PTCG_SETS.get(row["set"], []):
        for c in index.get(sid, {}).get(str(row["number"]).lower(), []):
            if _norm(c.get("name")) == _norm(row["name"]):
                return list(c.get("types") or [])
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ptcg-dir", type=Path, default=None,
                    help="directory with pokemon-tcg-data cards/en/<set>.json files")
    ap.add_argument("--db", type=Path, default=Path("data/pokemon.db"),
                    help="imported database, adds cards the cache no longer has")
    args = ap.parse_args()

    rows = _db_rows(args.db)
    rows.update(_cache_rows())              # the cache is authoritative where it has the card
    for r in rows.values():
        r["types"] = []

    if args.ptcg_dir:
        index = _ptcg_index(args.ptcg_dir)
        matched = unmatched = 0
        for r in rows.values():
            types = _types_for(r, index)
            if types is None:
                unmatched += 1
                continue
            matched += 1
            r["types"] = types
        print(f"types: {matched} matched by set+number+name, {unmatched} not found")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["card_id", "name", "set", "supertype", "types", "artist"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for cid in sorted(rows):
            r = rows[cid]
            if not r["artist"] and not r["supertype"] and not r["types"]:
                continue
            w.writerow({**{k: r[k] for k in fields}, "types": join_list(r["types"])})
    print(f"wrote {OUT} ({sum(1 for _ in OUT.open())-1} rows)")


if __name__ == "__main__":
    main()
