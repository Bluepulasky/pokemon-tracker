"""Bulk target quantities from a CSV.

Setting a target one card at a time across a 100+ card set is the tedium this
removes (issue #23).

Targets live on the card, not on the slot: `card_targets` is keyed by card_id
alone. So the file needs no set column — a target applies wherever that card
appears, which is both simpler than a per-set target and the reason the same
card cannot want two different quantities in two sets.

The parsing is deliberately forgiving about what a spreadsheet emits and strict
about what it means. Excel in a Spanish locale writes `;` separators and a
UTF-8 BOM; neither is the user's fault. An unknown card id is.
"""
from __future__ import annotations

import csv
import io

# Accepted spellings for each column. The issue proposed target_quantity;
# `target` is what the rest of the app calls it, so both are taken.
ID_KEYS = ("card_id", "id", "cardid")
TARGET_KEYS = ("target_quantity", "target", "quantity", "cantidad", "objetivo")
NAME_KEYS = ("card_name", "name", "nombre")

MAX_TARGET = 999


def _norm(header: str) -> str:
    return (header or "").strip().lower().replace(" ", "_").replace("﻿", "")


def _pick(row: dict, keys) -> str | None:
    for k in keys:
        if k in row and row[k] is not None:
            return str(row[k]).strip()
    return None


def parse_csv(text: str) -> tuple[list[dict], list[dict]]:
    """Return (rows, errors). A row is {card_id, target, name, line}.

    Never raises on bad input: a spreadsheet is user input, and the caller
    reports every problem at once rather than failing on the first one.
    """
    if not text.strip():
        return [], [{"line": 0, "error": "el archivo está vacío"}]

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        # A single-column file gives the sniffer nothing to go on.
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return [], [{"line": 0, "error": "no se encontró una cabecera"}]

    reader.fieldnames = [_norm(f) for f in reader.fieldnames]
    if not any(k in reader.fieldnames for k in ID_KEYS):
        return [], [{"line": 1,
                     "error": f"falta la columna card_id (encontradas: "
                              f"{', '.join(reader.fieldnames)})"}]
    if not any(k in reader.fieldnames for k in TARGET_KEYS):
        return [], [{"line": 1,
                     "error": f"falta la columna target_quantity (encontradas: "
                              f"{', '.join(reader.fieldnames)})"}]

    rows, errors, seen = [], [], {}
    for line, raw in enumerate(reader, start=2):
        card_id = _pick(raw, ID_KEYS)
        target = _pick(raw, TARGET_KEYS)

        if not card_id and not target:
            # An all-empty row: what Excel writes when a row's contents are
            # cleared instead of the row being deleted. Truly blank lines never
            # reach here, csv drops those itself.
            continue

        if not card_id:
            errors.append({"line": line, "error": "card_id vacío"})
            continue
        if target in (None, ""):
            errors.append({"line": line, "card_id": card_id,
                           "error": "target_quantity vacío"})
            continue
        try:
            value = int(float(target.replace(",", ".")))
        except ValueError:
            errors.append({"line": line, "card_id": card_id,
                           "error": f"target_quantity no es un número: {target!r}"})
            continue
        if value < 1:
            errors.append({"line": line, "card_id": card_id,
                           "error": f"el objetivo debe ser al menos 1, no {value}"})
            continue
        if value > MAX_TARGET:
            errors.append({"line": line, "card_id": card_id,
                           "error": f"el objetivo {value} supera el máximo de {MAX_TARGET}"})
            continue

        if card_id in seen:
            # Two rows for one card is a contradiction, not something to
            # resolve by whichever happens to be last.
            errors.append({"line": line, "card_id": card_id,
                           "error": f"card_id repetido, ya aparece en la línea {seen[card_id]}"})
            continue
        seen[card_id] = line
        rows.append({"card_id": card_id, "target": value,
                     "name": _pick(raw, NAME_KEYS), "line": line})

    return rows, errors


def apply_targets(repo, rows: list[dict]) -> dict:
    """Write the parsed rows, skipping cards the catalog does not have.

    Reports unchanged separately from updated: re-uploading the same file is a
    normal thing to do and should not read as 45 changes when nothing moved.
    """
    updated, unchanged, missing = [], [], []
    for row in rows:
        if not repo.get_card(row["card_id"]):
            missing.append({"line": row["line"], "card_id": row["card_id"],
                            "error": "no existe en el catálogo"})
            continue
        before = repo.get_card_target(row["card_id"])
        if before == row["target"]:
            unchanged.append(row["card_id"])
            continue
        repo.set_card_target(row["card_id"], row["target"])
        updated.append({"card_id": row["card_id"], "from": before,
                        "to": row["target"]})
    return {"updated": updated, "unchanged": unchanged, "missing": missing}
