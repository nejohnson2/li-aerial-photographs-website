"""Flask app for the Long Island Aerial Photography collection.

Pages:   / (map)   /gallery   /downloads
API:     /api/catalog  /api/footprints
         /api/geocode?q=<address>   — address -> coordinate (US Census, cached)
         /api/locate?lon=&lat=      — coordinate -> covering frames per survey
Tiles:   /tiles/<collection>/<z>/<x>/<y>.png  — dynamic XYZ tiles rendered
         from each survey's VRT mosaic with rio-tiler (no pre-generation).
Images:  /thumb/<collection>/<item_id>.jpg    — cached thumbnails
"""

import json
import logging
import math
import os
import threading
import urllib.parse
import urllib.request
from io import BytesIO

# GDAL tuning for tile serving from slow external storage — must be set before
# rasterio/rio-tiler are imported. The dataset pool must be large enough for
# several threads each holding a VRT with hundreds of proxied source files.
# (Do NOT set GDAL_DISABLE_READDIR_ON_OPEN here: it stops GDAL from finding
# the .ovr overview sidecar files and silently disables all overviews.)
os.environ.setdefault("GDAL_CACHEMAX", "512")
os.environ.setdefault("GDAL_MAX_DATASET_POOL_SIZE", "2000")

import rasterio
from flask import Flask, abort, jsonify, render_template, request, send_file, send_from_directory
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import Reader

from config import (
    CATALOG_PATH, COLLECTIONS, DATA_DIR, FOOTPRINTS_PATH, MOSAIC_CACHE, PORT, THUMB_DIR, TILE_CACHE,
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


# --- address search ----------------------------------------------------------

# Long Island bounding box: geocode hits outside it are rejected so "Main St"
# resolves to Long Island, not Manhattan or Albany.
LI_BBOX = (-74.05, 40.5, -71.7, 41.3)  # w, s, e, n
GEOCODE_CACHE_PATH = DATA_DIR / "geocode_cache.json"
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

_geocode_lock = threading.Lock()
_geocode_cache = None


def _load_geocode_cache():
    global _geocode_cache
    if _geocode_cache is None:
        _geocode_cache = json.loads(GEOCODE_CACHE_PATH.read_text()) if GEOCODE_CACHE_PATH.exists() else {}
    return _geocode_cache


def census_geocode(query):
    """Resolve an address via the US Census geocoder; returns dict or None."""
    q = query.strip()
    if "ny" not in q.lower() and "new york" not in q.lower():
        q += ", NY"
    url = CENSUS_URL + "?" + urllib.parse.urlencode(
        {"address": q, "benchmark": "Public_AR_Current", "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "li-aerial-photographs-website"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    w, s, e, n = LI_BBOX
    for m in data.get("result", {}).get("addressMatches", []):
        lon, lat = m["coordinates"]["x"], m["coordinates"]["y"]
        if w <= lon <= e and s <= lat <= n:
            return {"lon": lon, "lat": lat, "matched_address": m.get("matchedAddress", q)}
    return None


@app.route("/api/geocode")
def api_geocode():
    query = request.args.get("q", "").strip()
    if not query:
        abort(400, "missing q parameter")
    key = query.lower()
    with _geocode_lock:
        cache = _load_geocode_cache()
        if key in cache:
            return jsonify(cache[key]) if cache[key] else (jsonify({"error": "no match on Long Island"}), 404)
    try:
        result = census_geocode(query)
    except Exception as exc:
        log.warning("geocode failed for %r: %s", query, exc)
        return jsonify({"error": "geocoding service unavailable"}), 502
    with _geocode_lock:
        cache[key] = result
        DATA_DIR.mkdir(exist_ok=True)
        GEOCODE_CACHE_PATH.write_text(json.dumps(cache))
    if result is None:
        return jsonify({"error": "no match on Long Island"}), 404
    return jsonify(result)


def _mosaic_covers(collection, lon, lat):
    """True if the survey mosaic has real imagery at (lon, lat).

    Uses a decimated window read so the answer comes from the local overview
    files (~2-5 m precision) — no access to the source drive required.
    """
    with rasterio.open(mosaic_path(collection)) as src:
        xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
        row, col = src.index(xs[0], ys[0])
        if not (0 <= row < src.height and 0 <= col < src.width):
            return False
        win = Window(col - 4, row - 4, 8, 8)
        data = src.read(1, window=win, out_shape=(1, 1), boundless=True)
        return bool(data[0, 0] != 0)


_footprints = None


def _load_footprints():
    global _footprints
    if _footprints is None:
        _footprints = json.loads(FOOTPRINTS_PATH.read_text())["features"]
    return _footprints


@app.route("/api/locate")
def api_locate():
    try:
        lon = float(request.args.get("lon", ""))
        lat = float(request.args.get("lat", ""))
    except ValueError:
        abort(400, "lon and lat are required")

    # bbox prefilter, grouped by survey
    candidates = {}
    for f in _load_footprints():
        c = f["geometry"]["coordinates"][0]
        w, s = c[0]
        e, n = c[2]
        if w <= lon <= e and s <= lat <= n:
            cx, cy = (w + e) / 2, (s + n) / 2
            dist_m = math.hypot((lon - cx) * 85000 * math.cos(math.radians(lat)), (lat - cy) * 111000)
            candidates.setdefault(f["properties"]["collection"], []).append({
                "id": f["properties"]["id"],
                "frame": f["properties"]["frame"],
                "distance_m": round(dist_m),
            })

    surveys = []
    for cid, frames in candidates.items():
        try:
            covered = _mosaic_covers(cid, lon, lat)
        except Exception:
            log.exception("coverage check failed for %s", cid)
            covered = True  # fall back to the bbox answer rather than hiding frames
        frames.sort(key=lambda fr: fr["distance_m"])
        surveys.append({
            "collection": cid,
            "name": COLLECTIONS[cid]["name"],
            "year": COLLECTIONS[cid]["year"],
            "covered": covered,
            "frames": frames,
        })
    def year_key(s):
        digits = "".join(ch for ch in s["year"] if ch.isdigit())
        return int(digits[:4]) if digits else 9999

    surveys.sort(key=year_key)
    return jsonify({"lon": lon, "lat": lat, "surveys": surveys})


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


_fallback_warned = set()


def render_tile(collection, z, x, y):
    """Render a tile; returns (png_bytes, has_imagery, full_quality).

    Deep-zoom tiles need base-resolution pixels from the data volume. If that
    read fails (drive unplugged), retry at smaller tile sizes: the coarser
    read resolves from the local .ovr overviews, and the browser stretches the
    smaller PNG across the tile — soft, but the imagery never disappears.

    Fully-masked and fallback tiles are never disk-cached, so full-quality
    tiles get rendered and cached once the volume is back.
    """
    vrt = mosaic_path(collection)
    last_exc = None
    with _render_slots:
        for tilesize in (256, 128, 64, 32):
            try:
                with Reader(vrt) as src:
                    tile = src.tile(x, y, z, tilesize=tilesize)
                if tilesize != 256 and collection not in _fallback_warned:
                    _fallback_warned.add(collection)
                    log.warning("%s: base rasters unreachable (data drive unplugged?) — "
                                "serving upscaled overview tiles", collection)
                return tile.render(img_format="PNG"), bool(tile.mask.any()), tilesize == 256
            except TileOutsideBounds:
                raise
            except Exception as exc:
                last_exc = exc
    raise last_exc


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
        png, has_imagery, full_quality = render_tile(collection, z, x, y)
        cacheable = has_imagery and full_quality
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
    # Fallback/empty tiles get a short browser cache so full-quality versions
    # replace them quickly once the data volume is back.
    resp.cache_control.max_age = 3600 if cacheable else 60
    return resp


if __name__ == "__main__":
    # threaded=True lets a map view's ~100 simultaneous tile requests render in
    # parallel (GDAL releases the GIL during I/O and decode) instead of queueing.
    app.run(host="127.0.0.1", port=PORT, debug=True, threaded=True)
