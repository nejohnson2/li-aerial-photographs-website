"""Central configuration for the LI Aerial Photographs website.

Collection definitions describe where each survey lives under DATA_ROOT and
which VRT mosaic (if any) provides the authoritative list of georeferenced
frames for the map.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/path/to/LI-Aerial-Photography"))
COMMONS_ROOT = DATA_ROOT / "from_digital_commons"

# Generated artifacts
DATA_DIR = PROJECT_ROOT / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
FOOTPRINTS_PATH = DATA_DIR / "footprints.geojson"
THUMB_DIR = PROJECT_ROOT / "cache" / "thumbs"
# Local VRT copies with overviews (built by `make overviews`) — used for tile
# serving when present so the read-only data volume never gets .ovr files.
MOSAIC_CACHE = PROJECT_ROOT / "cache" / "mosaics"
# Rendered map tiles are cached here permanently; each tile renders once ever.
TILE_CACHE = PROJECT_ROOT / "cache" / "tiles"
THUMB_SIZE = 400  # max edge in pixels

PORT = int(os.environ.get("PORT", 5050))

# survey id -> definition
COLLECTIONS = {
    "NC-1938": {
        "name": "Nassau County 1938",
        "county": "Nassau",
        "year": "1938",
        "path": COMMONS_ROOT / "Nassau_County" / "NC-1938",
        "vrt": None,
        "color": "#e05c5c",
        "description": "USDA Agricultural Adjustment Administration survey, 1:20,000. Not georeferenced.",
    },
    "NC-1947": {
        "name": "Nassau County 1947",
        "county": "Nassau",
        "year": "1947",
        "path": COMMONS_ROOT / "Nassau_County" / "NC-1947",
        "vrt": None,
        "color": "#e0a05c",
        "description": "Nassau County survey, 1947. Not georeferenced.",
    },
    "SC-1938": {
        "name": "Suffolk County 1938",
        "county": "Suffolk",
        "year": "1938",
        "path": COMMONS_ROOT / "Suffolk_County" / "SC-1938",
        "vrt": COMMONS_ROOT / "Suffolk_County" / "SC-1938" / "SC-1938.vrt",
        "color": "#4c9f70",
        "description": "USDA survey of Suffolk County, 1938.",
    },
    "SC-1938-ASA": {
        "name": "Suffolk County 1938 (ASA)",
        "county": "Suffolk",
        "year": "~1930-1938",
        "path": COMMONS_ROOT / "Suffolk_County" / "SC-1938-ASA",
        "vrt": COMMONS_ROOT / "Suffolk_County" / "SC-1938-ASA" / "1938_highres_mosaic.vrt",
        "registration_report": COMMONS_ROOT / "Suffolk_County" / "SC-1938-ASA" / "registration_report.csv",
        "color": "#3d7ea6",
        "description": "Air Map Corporation of America survey for the Suffolk County Regional Planning Board.",
    },
    "SC-1947": {
        "name": "Suffolk County 1947",
        "county": "Suffolk",
        "year": "1947",
        "path": COMMONS_ROOT / "Suffolk_County" / "SC-1947",
        "vrt": COMMONS_ROOT / "Suffolk_County" / "SC-1947" / "SC-1947_mosaic.vrt",
        "color": "#8a6bbe",
        "description": "Suffolk County survey, September 1947.",
    },
    "SC-1970": {
        "name": "Suffolk County 1970",
        "county": "Suffolk",
        "year": "1970",
        "path": COMMONS_ROOT / "Suffolk_County" / "SC-1970",
        "vrt": COMMONS_ROOT / "Suffolk_County" / "SC-1970" / "SC-1970_mosaic.vrt",
        "color": "#b85c8a",
        "description": "Soil Conservation Service / Lockwood, Kessler & Bartlett survey flown 1970-05-30, 1:50,000.",
    },
    "LOOSE-1938": {
        "name": "1938 Shinnecock area (unfiled)",
        "county": "Suffolk",
        "year": "1938",
        "path": COMMONS_ROOT,  # loose numbered folders 000001-000006
        "loose_items": ["000001", "000002", "000003", "000004", "000005", "000006"],
        "vrt": None,
        "color": "#7d7d7d",
        "description": "Six loose 1938 Shinnecock-area aerials from an unknown compilation source.",
    },
}
