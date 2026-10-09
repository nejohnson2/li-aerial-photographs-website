"""Build the unified item catalog and footprint GeoJSON from the data volume.

Walks every item folder in each collection, parses its metadata.json, and — for
frames referenced by the survey's VRT mosaic — reads the georeferenced raster's
bounds (header only) to produce a WGS84 footprint polygon.

Outputs:
    data/catalog.json        — one record per item (metadata, links, geo status)
    data/footprints.geojson  — FeatureCollection of frame bounding boxes
"""

import csv
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import CATALOG_PATH, COLLECTIONS, DATA_DIR, FOOTPRINTS_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_catalog")

IMAGE_EXTS = {".tif", ".tiff", ".jpeg", ".jpg", ".png"}


def vrt_sources(vrt_path):
    """Map item folder id -> georeferenced source file (relative to the VRT dir)."""
    sources = {}
    root = ET.parse(vrt_path).getroot()
    for el in root.iter("SourceFilename"):
        rel = el.text.strip()
        item_id = rel.split("/")[0]
        sources[item_id] = rel
    return sources


def registration_towns(csv_path):
    towns = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("town"):
                towns[row["id"]] = row["town"]
    return towns


def parse_metadata(item_dir):
    meta_path = item_dir / "metadata.json"
    if not meta_path.exists():
        return {}
    with open(meta_path) as f:
        return json.load(f)


def pick_frame_name(item_dir, meta):
    """Frame name: prefer an image filename stem, fall back to the catalog title token."""
    for f in sorted(item_dir.iterdir()):
        if f.suffix.lower() in IMAGE_EXTS:
            stem = f.stem
            # strip georeferencing suffixes so all variants share one name
            return re.sub(r"(_georef(_nu)?|_modified|_cor)$", "", stem)
    fields = meta.get("fields", {})
    for key, value in fields.items():
        if "Collection" in key and isinstance(value, str) and value:
            return value.split()[0]
    return item_dir.name


def preview_file(item_dir):
    """Best local file to build a thumbnail from: JPEG preview if present, else a TIFF."""
    jpegs = sorted(p for p in item_dir.iterdir() if p.suffix.lower() in {".jpeg", ".jpg"})
    if jpegs:
        return jpegs[0]
    tifs = sorted(p for p in item_dir.iterdir() if p.suffix.lower() in {".tif", ".tiff"})
    return tifs[0] if tifs else None


def footprint(raster_path):
    """WGS84 bounding box of a georeferenced raster, reading only the header."""
    with rasterio.open(raster_path) as src:
        if src.crs is None:
            return None
        b = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
    w, s, e, n = b
    return {
        "type": "Polygon",
        "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    }


def item_dirs(coll_id, coll):
    if "loose_items" in coll:
        return [coll["path"] / i for i in coll["loose_items"]]
    return sorted(p for p in coll["path"].iterdir() if p.is_dir() and re.fullmatch(r"\d{6}", p.name))


def main():
    DATA_DIR.mkdir(exist_ok=True)
    catalog, features = [], []
    stats = {}

    for coll_id, coll in COLLECTIONS.items():
        sources = vrt_sources(coll["vrt"]) if coll.get("vrt") else {}
        towns = registration_towns(coll["registration_report"]) if coll.get("registration_report") else {}
        dirs = item_dirs(coll_id, coll)
        n_geo = 0

        for item_dir in tqdm(dirs, desc=coll_id):
            item_id = item_dir.name
            meta = parse_metadata(item_dir)
            fields = meta.get("fields", {})
            links = meta.get("links", {})
            pv = preview_file(item_dir)

            record = {
                "id": item_id,
                "collection": coll_id,
                "frame": pick_frame_name(item_dir, meta),
                "county": coll["county"],
                "year": coll["year"],
                "date": fields.get("Date", ""),
                "town": towns.get(item_id, ""),
                "coverage": fields.get("Coverage", ""),
                "author": fields.get("Author", fields.get("Creator", "")),
                "description": fields.get("Description", ""),
                "item_url": meta.get("item_url", ""),
                "links": {k: links.get(k, "") for k in ("native", "medium", "thumbnail")},
                "preview_file": pv.name if pv else None,
                "georeferenced": False,
            }

            if item_id in sources:
                raster = coll["path"] / sources[item_id]
                try:
                    geom = footprint(raster)
                except Exception as exc:  # unreadable raster: keep item, drop footprint
                    log.warning("footprint failed for %s/%s: %s", coll_id, item_id, exc)
                    geom = None
                if geom:
                    record["georeferenced"] = True
                    n_geo += 1
                    features.append({
                        "type": "Feature",
                        "id": f"{coll_id}/{item_id}",
                        "properties": {
                            "id": item_id,
                            "collection": coll_id,
                            "frame": record["frame"],
                            "town": record["town"],
                            "date": record["date"],
                        },
                        "geometry": geom,
                    })

            catalog.append(record)

        stats[coll_id] = {"items": len(dirs), "georeferenced": n_geo}
        log.info("%s: %d items, %d georeferenced", coll_id, len(dirs), n_geo)

    with open(CATALOG_PATH, "w") as f:
        json.dump({"collections": {k: {kk: vv for kk, vv in v.items() if kk not in ("path", "vrt", "registration_report", "loose_items")}
                                    for k, v in COLLECTIONS.items()},
                   "stats": stats,
                   "items": catalog}, f)
    with open(FOOTPRINTS_PATH, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    log.info("wrote %d items -> %s", len(catalog), CATALOG_PATH)
    log.info("wrote %d footprints -> %s", len(features), FOOTPRINTS_PATH)


if __name__ == "__main__":
    main()
