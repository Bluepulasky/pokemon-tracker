"""Checks for the failure this app keeps having.

Five bugs so far came from the same shape, none of them raised, and none of
them failed a test:

  * a condition grade was renamed, leaving cards stored under a grade the app
    no longer offers — invisible in filters, sorted to the bottom silently
  * the source spells one rarity three ways, so a rule excluding "Rare Holo"
    kept three holos and built a 51-card set called 48
  * a card number arrives as "BS 4" on some rows and 4 on others, so one card
    became two
  * print runs were inferred from a hardcoded list of catalogue set ids, so a
    set that plainly had a 1st Edition was reported as never having had one
  * the same list decided the era, so every Base Set common was offered as a
    reverse holo — a variant that did not exist until 2002

The common thread is a lookup that misses and returns something plausible. An
unlisted grade sorts last. An unknown set id is "modern". Each answer is
reasonable in isolation and wrong in fact, and nothing anywhere says so.

These checks look for the mismatch itself rather than its consequences, so the
next rename is a warning on a page instead of a wrong price nobody questions.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Reverse holos begin with Legendary Collection; anything earlier cannot have
# one, and a set with no release date cannot be judged either way.
REVERSE_HOLO_FROM = "2002/05/24"


def _finding(level: str, check: str, message: str, detail=None) -> dict:
    return {"level": level, "check": check, "message": message,
            "detail": detail or []}


def check_conditions(repo, conditions) -> list[dict]:
    """Every stored grade must be one the app still offers.

    A card left on a renamed grade drops out of the condition filter and sorts
    to the bottom without a word, so a stale grade is worth flagging.
    """
    out = []
    rows = repo._all(
        "SELECT DISTINCT condition FROM collection_items WHERE condition IS NOT NULL")
    unknown = sorted({r["condition"] for r in rows} - set(conditions))
    if unknown:
        out.append(_finding(
            "error", "conditions",
            f"{len(unknown)} condición(es) de tus cartas ya no están en el "
            f"vocabulario actual.",
            unknown))
    return out


def check_rarities(repo) -> list[dict]:
    """Two spellings of one rarity make a rule quietly select the wrong cards."""
    rows = repo._all(
        "SELECT DISTINCT rarity FROM cards WHERE rarity IS NOT NULL AND rarity <> ''")
    # Sorted words, not just lowercase: the spellings that actually collided
    # were "Rare Holo" and "Holo Rare", which differ by order and would hash
    # apart under any gentler comparison. Lowercasing alone would have missed
    # the very bug this check exists for.
    def fingerprint(value: str) -> str:
        return " ".join(sorted(value.strip().lower().split()))

    seen: dict[str, list[str]] = {}
    for r in rows:
        seen.setdefault(fingerprint(r["rarity"]), []).append(r["rarity"])
    clashes = {k: v for k, v in seen.items() if len(set(v)) > 1}

    out = []
    if clashes:
        out.append(_finding(
            "error", "rarities",
            "La misma rareza está guardada de más de una forma. Una regla que "
            "excluye una escritura deja pasar las otras en silencio.",
            [" / ".join(sorted(set(v))) for v in clashes.values()]))

    blank = repo._one(
        "SELECT COUNT(*) AS n FROM cards WHERE rarity IS NULL OR rarity = ''")
    if blank and blank["n"]:
        out.append(_finding(
            "warning", "rarities",
            f"{blank['n']} carta(s) no tienen rareza, así que cualquier regla de "
            f"rareza las saltea en silencio.", []))
    return out


def check_set_dates(repo) -> list[dict]:
    """Without a release date the era has to be guessed from the set id."""
    rows = repo._all(
        "SELECT id, name FROM official_sets "
        " WHERE release_date IS NULL OR release_date = ''")
    if not rows:
        return []
    return [_finding(
        "warning", "set_dates",
        f"{len(rows)} set(s) no tienen fecha de salida. Qué tiradas y variantes "
        f"existen se infiere entonces del id del set, que es lo que ofrecía "
        f"reverse holos en Base Set.",
        [f"{r['id']} {r['name']}" for r in rows])]


def check_card_numbers(repo) -> list[dict]:
    """A number that still carries its set code means the id was built wrong."""
    rows = repo._all(
        "SELECT id, number FROM cards WHERE number LIKE '% %' OR number = ''")
    if not rows:
        return []
    return [_finding(
        "error", "card_numbers",
        f"{len(rows)} número(s) de carta se ven mal — un número no debería tener "
        f"un espacio. Así es como una carta se partió en dos.",
        [f"{r['id']} -> {r['number']!r}" for r in rows[:10]])]


def check_products(repo) -> list[dict]:
    """A set with no products imported answers the version picker from the network."""
    try:
        rows = repo._all(
            """SELECT s.id, s.name FROM official_sets s
                WHERE NOT EXISTS (SELECT 1 FROM market_products m
                                   WHERE m.card_id LIKE s.id || '-%')""")
    except Exception:                                        # noqa: BLE001
        return []                        # table not present; nothing to say
    if not rows:
        return []
    return [_finding(
        "info", "products",
        f"{len(rows)} set(s) del catálogo viejo no tienen productos importados. "
        f"Sus cartas cuestan una consulta cada vez que las abrís. Si ya "
        f"importaste ese set desde Mantenimiento, quedó como un set nuevo "
        f"aparte (ej. \"bs\" en vez de \"base1\").",
        [f"{r['id']} {r['name']}" for r in rows])]


def run_checks(repo, conditions) -> dict:
    findings: list[dict] = []
    for fn, args in ((check_conditions, (repo, conditions)),
                     (check_rarities, (repo,)),
                     (check_set_dates, (repo,)),
                     (check_card_numbers, (repo,)),
                     (check_products, (repo,))):
        try:
            findings.extend(fn(*args))
        except Exception:                                    # noqa: BLE001
            log.warning("health check %s failed", fn.__name__, exc_info=True)
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["level"], 3))
    return {
        "ok": not any(f["level"] == "error" for f in findings),
        "errors": sum(1 for f in findings if f["level"] == "error"),
        "warnings": sum(1 for f in findings if f["level"] == "warning"),
        "findings": findings,
    }
