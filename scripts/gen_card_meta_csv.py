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

from tombot.services.tcggo_catalog import card_id_for, split_code

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
    rows: dict[str, dict] = {}
    for c in _records():
        prefix, number = split_code(c.get("card_code_number") or "")
        cid = card_id_for(prefix, number)
        if not cid or cid.endswith("-"):
            continue
        artist = _artist(c.get("artist"))
        supertype = c.get("supertype") or ""
        cur = rows.get(cid)
        # One row per card. A colliding id (two different cards share a code, e.g.
        # Celebrations base vs Classic Collection) prefers the base card — the
        # Classic Collection entry is a separate concern and its rarity marks it.
        is_cc = (c.get("rarity") or "") == "Classic Collection"
        if cur is None:
            rows[cid] = {"card_id": cid, "name": c.get("name") or "",
                         "set": prefix.upper(), "supertype": supertype,
                         "artist": artist, "_cc": is_cc}
        elif cur.get("_cc") and not is_cc:
            rows[cid] = {"card_id": cid, "name": c.get("name") or "",
                         "set": prefix.upper(), "supertype": supertype,
                         "artist": artist, "_cc": is_cc}
        else:
            # Fill any blank the winning record left.
            cur["artist"] = cur["artist"] or artist
            cur["supertype"] = cur["supertype"] or supertype

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
