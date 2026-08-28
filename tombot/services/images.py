"""Photo upload pipeline.

The spec makes mobile camera upload a priority but does not address what actually
breaks there:
  - iOS Safari uploads HEIC; browsers cannot render it and Pillow cannot open it
    without pillow-heif. Photos would upload and then show as broken images.
  - Phone photos are 4-12MB; without a cap and a resize the grid is unusable on
    mobile data.
  - EXIF orientation makes portrait photos display sideways.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)

try:                                    # optional: only needed for iOS HEIC uploads
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:                       # pragma: no cover
    HEIF_OK = False
    log.warning("pillow-heif not available: iPhone HEIC uploads will be rejected")

ALLOWED_PREFIX = "image/"


class ImageError(ValueError):
    pass


def process_upload(file_storage, config) -> dict:
    """Normalise an uploaded photo to JPEG + thumbnail. Returns the photo record."""
    mimetype = (file_storage.mimetype or "").lower()
    if not mimetype.startswith(ALLOWED_PREFIX):
        raise ImageError(f"tipo de archivo no soportado: {mimetype or 'desconocido'}")
    if mimetype in ("image/heic", "image/heif") and not HEIF_OK:
        raise ImageError("formato HEIC no soportado en este servidor (instala pillow-heif)")

    try:
        img = Image.open(file_storage.stream)
    except UnidentifiedImageError as e:
        raise ImageError("no se pudo leer la imagen") from e

    img = ImageOps.exif_transpose(img)           # phone photos are often sideways
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    stem = uuid.uuid4().hex
    name = f"{stem}.jpg"
    thumb_name = f"{stem}_t.jpg"

    full = img.copy()
    full.thumbnail((config.IMAGE_MAX_EDGE, config.IMAGE_MAX_EDGE), Image.LANCZOS)
    dest = Path(config.COLLECTION_IMG_DIR) / name
    full.save(dest, "JPEG", quality=config.JPEG_QUALITY, optimize=True)

    thumb = img.copy()
    thumb.thumbnail((config.THUMB_MAX_EDGE, config.THUMB_MAX_EDGE), Image.LANCZOS)
    thumb.save(Path(config.THUMB_DIR) / thumb_name, "JPEG",
               quality=config.JPEG_QUALITY, optimize=True)

    return {
        "filename": f"collection/{name}",
        "thumb_filename": f"thumbs/{thumb_name}",
        "width": full.width,
        "height": full.height,
        "bytes": dest.stat().st_size,
    }


def delete_files(rel_paths, config) -> None:
    """Best-effort unlink. A missing file must not fail the API call that removed
    the database row — the row is the source of truth."""
    for rel in rel_paths:
        try:
            (Path(config.MEDIA_DIR) / rel).unlink(missing_ok=True)
        except OSError as e:
            log.warning("could not delete %s: %s", rel, e)
