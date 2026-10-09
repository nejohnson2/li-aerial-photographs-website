"""Pre-generate thumbnails for every catalog item into cache/thumbs/.

JPEG previews are resized with Pillow; items with only TIFFs (e.g. SC-1938,
the loose 1938 items) are read with rasterio using a decimated read so the
full-resolution scan is never loaded into memory.
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import CATALOG_PATH, COLLECTIONS, THUMB_DIR, THUMB_SIZE

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_thumbnails")

Image.MAX_IMAGE_PIXELS = None  # scans exceed Pillow's decompression-bomb default


def item_source(record):
    coll = COLLECTIONS[record["collection"]]
    if not record["preview_file"]:
        return None
    return coll["path"] / record["id"] / record["preview_file"]


def thumb_from_tif(src_path, out_path):
    with rasterio.open(src_path) as src:
        scale = max(src.width, src.height) / THUMB_SIZE
        out_w = max(1, round(src.width / scale))
        out_h = max(1, round(src.height / scale))
        data = src.read(out_shape=(src.count, out_h, out_w))
    if data.dtype != np.uint8:
        lo, hi = np.percentile(data, (1, 99))
        data = np.clip((data - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
    img = Image.fromarray(data[0] if data.shape[0] == 1 else np.moveaxis(data[:3], 0, -1))
    img.convert("RGB").save(out_path, "JPEG", quality=85)


def thumb_from_jpeg(src_path, out_path):
    img = Image.open(src_path)
    img.thumbnail((THUMB_SIZE, THUMB_SIZE))
    img.convert("RGB").save(out_path, "JPEG", quality=85)


def main():
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_PATH) as f:
        items = json.load(f)["items"]

    made = skipped = failed = 0
    for record in tqdm(items, desc="thumbnails"):
        out_path = THUMB_DIR / f"{record['collection']}_{record['id']}.jpg"
        if out_path.exists():
            skipped += 1
            continue
        src_path = item_source(record)
        if src_path is None or not src_path.exists():
            failed += 1
            continue
        try:
            if src_path.suffix.lower() in {".jpeg", ".jpg"}:
                thumb_from_jpeg(src_path, out_path)
            else:
                thumb_from_tif(src_path, out_path)
            made += 1
        except Exception as exc:
            log.warning("thumbnail failed for %s/%s: %s", record["collection"], record["id"], exc)
            failed += 1

    log.info("thumbnails: %d created, %d existing, %d failed", made, skipped, failed)


if __name__ == "__main__":
    main()
