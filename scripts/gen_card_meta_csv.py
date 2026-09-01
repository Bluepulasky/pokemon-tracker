"""Regenerate the pre-baked card-metadata fix file from the tcggo cache.

tcggo returns the illustrator and supertype on every card record, but imports
that ran before those columns existed never stored them. This scans the on-disk
tcggo response cache and writes tombot/data/card_meta.csv — a card_id -> {artist,
supertype} table shipped with the app so any install can fill the gaps offline
(see `flask fix-card-meta` / Mantenimiento), with no re-import and no API cost.

Run from the repo root:  .venv/bin/python scripts/gen_card_meta_csv.py
"""
from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

from tombot.services.tcggo_catalog import (card_id_for, resolve_collisions,
                                           split_code)

OUT = Path("tombot/data/card_meta.csv")
CACHE_GLOBS = [".cache/**/*.json", "data/.cache-tcggo/*.json"]


def _artist(a):
    if isinstance(a, dict):
        return a.get("name") or a.get("slug") or ""
    return a or ""


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


def main() -> None:
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
            "name": c.get("name") or "", "set": prefix.upper(),
            "artist": _artist(c.get("artist")), "supertype": c.get("supertype") or "",
        })
    resolve_collisions(products)

    rows: dict[str, dict] = {}
    for p in products:
        cur = rows.get(p["card_id"])
        if cur is None:
            rows[p["card_id"]] = {"card_id": p["card_id"], "name": p["name"],
                                  "set": p["set"], "supertype": p["supertype"],
                                  "artist": p["artist"]}
        else:                                   # fill any blank a sibling left
            cur["artist"] = cur["artist"] or p["artist"]
            cur["supertype"] = cur["supertype"] or p["supertype"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["card_id", "name", "set", "supertype", "artist"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for cid in sorted(rows):
            r = rows[cid]
            if not r["artist"] and not r["supertype"]:
                continue
            w.writerow({k: r[k] for k in fields})
    print(f"wrote {OUT} ({sum(1 for _ in OUT.open())-1} rows)")


if __name__ == "__main__":
    main()
