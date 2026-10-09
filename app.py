"""Flask app for the Long Island Aerial Photography collection.

Pages:   / (map)   /gallery   /downloads
API:     /api/catalog  /api/footprints
Tiles:   /tiles/<collection>/<z>/<x>/<y>.png  — dynamic XYZ tiles rendered
         from each survey's VRT mosaic with rio-tiler (no pre-generation).
Images:  /thumb/<collection>/<item_id>.jpg    — cached thumbnails
"""

import json
import logging
import os
import threading
from io import BytesIO

# GDAL tuning for tile serving from slow external storage — must be set before
# rasterio/rio-tiler are imported. The dataset pool must be large enough for
# several threads each holding a VRT with hundreds of proxied source files.
# (Do NOT set GDAL_DISABLE_READDIR_ON_OPEN here: it stops GDAL from finding
# the .ovr overview sidecar files and silently disables all overviews.)
os.environ.setdefault("GDAL_CACHEMAX", "512")
os.environ.setdefault("GDAL_MAX_DATASET_POOL_SIZE", "2000")

from flask import Flask, abort, jsonify, render_template, send_file, send_from_directory
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import Reader

from config import (
    CATALOG_PATH, COLLECTIONS, FOOTPRINTS_PATH, MOSAIC_CACHE, PORT, THUMB_DIR, TILE_CACHE,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")
# GDAL relays every internal notice through this logger (harmless NoData/warp
# warnings included); only surface actual errors.
logging.getLogger("rasterio._err").setLevel(logging.ERROR)

app = Flask(__name__)

TILE_COLLECTIONS = {cid: c for cid, c in COLLECTIONS.items() if c.get("vrt")}


def load_catalog():
    if not CATALOG_PATH.exists():
        abort(503, "Catalog not built yet — run `make catalog`.")
    with open(CATALOG_PATH) as f:
        return json.load(f)


@app.route("/")
def map_page():
    return render_template("map.html", collections=COLLECTIONS, active="map")


@app.route("/gallery")
def gallery_page():
    return render_template("gallery.html", collections=COLLECTIONS, active="gallery")


@app.route("/downloads")
def downloads_page():
    return render_template("downloads.html", collections=COLLECTIONS, active="downloads")


@app.route("/api/catalog")
def api_catalog():
    return jsonify(load_catalog())


@app.route("/api/footprints")
def api_footprints():
    if not FOOTPRINTS_PATH.exists():
        abort(503, "Footprints not built yet — run `make catalog`.")
    with open(FOOTPRINTS_PATH) as f:
        return jsonify(json.load(f))


@app.route("/thumb/<collection>/<item_id>.jpg")
def thumb(collection, item_id):
    return send_from_directory(THUMB_DIR, f"{collection}_{item_id}.jpg", max_age=86400)


# --- dynamic tiles -----------------------------------------------------------

# 1x1 transparent PNG for tiles outside a mosaic's bounds
_EMPTY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8ffff3f0300050001010005186824000000004945"
    "4e44ae426082"
)


def mosaic_path(collection):
    cached = MOSAIC_CACHE / f"{collection}.vrt"
    return str(cached if cached.exists() else TILE_COLLECTIONS[collection]["vrt"])


# The threaded server accepts every tile request at once, but only this many
# render concurrently — more would exhaust GDAL's dataset pool and thrash the
# external drive. Cached tiles bypass this entirely.
_render_slots = threading.BoundedSemaphore(8)


def render_tile(collection, z, x, y):
    """Render a tile; returns (png_bytes, has_imagery).

    Fully-masked tiles are never disk-cached: they're cheap to re-render, and a
    blank produced while an overview file is being rebuilt must not be stored
    permanently.
    """
    vrt = mosaic_path(collection)
    with _render_slots, Reader(vrt) as src:
        tile = src.tile(x, y, z, tilesize=256)
    return tile.render(img_format="PNG"), bool(tile.mask.any())


@app.route("/tiles/<collection>/<int:z>/<int:x>/<int:y>.png")
def tiles(collection, z, x, y):
    if collection not in TILE_COLLECTIONS:
        abort(404)

    # Persistent disk cache: each tile is rendered once, ever.
    cache_path = TILE_CACHE / collection / str(z) / str(x) / f"{y}.png"
    if cache_path.exists():
        resp = send_file(cache_path, mimetype="image/png")
        resp.cache_control.max_age = 86400
        return resp

    cacheable = False
    try:
        png, cacheable = render_tile(collection, z, x, y)
    except TileOutsideBounds:
        png = _EMPTY_PNG
    except Exception:
        log.exception("tile %s/%d/%d/%d failed", collection, z, x, y)
        abort(500)

    if cacheable:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(f".{os.getpid()}.{id(png)}.tmp")
        tmp.write_bytes(png)
        tmp.replace(cache_path)  # atomic, safe under concurrent requests

    resp = send_file(BytesIO(png), mimetype="image/png")
    resp.cache_control.max_age = 3600
    return resp


if __name__ == "__main__":
    # threaded=True lets a map view's ~100 simultaneous tile requests render in
    # parallel (GDAL releases the GIL during I/O and decode) instead of queueing.
    app.run(host="127.0.0.1", port=PORT, debug=True, threaded=True)
