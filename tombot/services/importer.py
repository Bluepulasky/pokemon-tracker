"""Catalog import. Resumable, set by set.

Spec §20: external data must never overwrite collection state. The importer only
writes official_sets and cards; it never touches collection_sets, set_slots,
collection_items or photos.
"""
from __future__ import annotations

import logging
from pathlib import Path

import requests

log = logging.getLogger(__name__)


class CatalogImporter:
    def __init__(self, repo, source, config):
        self.repo = repo
        self.source = source
        self.config = config

    def import_sets(self, set_ids: list[str]) -> dict:
        result = {"sets": {}, "cards": 0, "failed": []}
        for sid in set_ids:
            try:
                meta = self.source.fetch_set(sid)
                self.repo.upsert_official_set(meta)
                cards = list(self.source.fetch_cards(sid))
                n = self.repo.upsert_cards(cards)
                result["sets"][sid] = n
                result["cards"] += n
                log.info("imported %s: %d cards", sid, n)
            except Exception as e:
                # One flaky set must not lose the sets already imported.
                log.error("import failed for %s: %s", sid, e)
                result["failed"].append({"set": sid, "error": str(e)})
        self.repo.set_meta("last_catalog_import", str(result["cards"]))
        return result

    def cache_images(self, limit: int = 5000) -> dict:
        """Download catalog thumbnails locally so the grid does not depend on a
        third-party CDN on every page load (PLAN.md §2.14). ~40MB for 1,100 cards."""
        target: Path = self.config.CATALOG_IMG_DIR
        target.mkdir(parents=True, exist_ok=True)
        todo = self.repo.cards_missing_local_image(limit)
        ok = fail = 0
        with requests.Session() as s:
            s.headers["User-Agent"] = "tombot-pokemon-tracker/0.1"
            for row in todo:
                dest = target / f"{row['id']}.png"
                try:
                    if not dest.exists():
                        r = s.get(row["image_small_url"], timeout=self.config.HTTP_TIMEOUT)
                        r.raise_for_status()
                        dest.write_bytes(r.content)
                    self.repo.set_card_image_local(row["id"], f"catalog/{dest.name}")
                    ok += 1
                except Exception as e:
                    log.warning("image download failed for %s: %s", row["id"], e)
                    fail += 1
        return {"downloaded": ok, "failed": fail, "remaining": max(0, len(todo) - ok)}
