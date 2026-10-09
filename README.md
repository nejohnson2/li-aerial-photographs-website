# Long Island Aerial Photography Website

Interactive website for exploring Stony Brook University's Long Island historical
aerial photography collection (1938–1970). Local Flask proof of concept.

## Features

- **Map** (`/`): the four Suffolk County survey mosaics (592 georeferenced
  frames) as zoomable imagery overlays on a Google satellite basemap, rendered
  dynamically from the GDAL VRT mosaics — no tile pre-generation. Clicking the
  imagery identifies the frame under the cursor and shows its photograph,
  metadata, and download links (frame extents are invisible click targets that
  highlight on hover). Search by frame name, town, or date flies to the frame.
- **Gallery** (`/gallery`): browsable card grid of all 721 items, including the
  non-georeferenced ones (97 Nassau County items, 6 loose 1938 Shinnecock
  items, SC-1970 frames 181/184), with collection filters and full metadata.
- **Downloads** (`/downloads`): filter and multi-select items or whole
  collections, then export a link manifest (`.txt`) or a `curl` fetch script
  (`.sh`) pointing at the SBU Academic Commons native-resolution downloads.
  No imagery is redistributed by this server.
- **Address search** (map and gallery): type a street address (e.g.
  `120 Main St, Bay Shore`) and the site geocodes it via the free US Census
  geocoder (no API key; results cached in `data/geocode_cache.json`, biased to
  a Long Island bounding box) and finds every survey whose imagery actually
  covers that point — confirmed by sampling the mosaic pixel, not just frame
  bounding boxes. The map drops a marker, enables the covering surveys, and
  lists frames by year ("this location through time"); the gallery filters its
  grid to the covering frames. Note: the Census geocoder resolves street
  addresses, not bare place names — town names are handled by the regular
  text search.

## Data

The site reads (read-only) from the collection drive; nothing is written to it.
Set the location in `.env`:

```
DATA_ROOT=/path/to/LI-Aerial-Photography
```

Surveys served (from `from_digital_commons/`):

| Collection | Items | Georeferenced | Map imagery |
|------------|-------|---------------|-------------|
| NC-1938 | 80 | 0 | — |
| NC-1947 | 17 | 0 | — |
| SC-1938 | 156 | 152 | VRT mosaic |
| SC-1938-ASA | 375 | 358 | VRT mosaic (high-res) |
| SC-1947 | 35 | 34 | VRT mosaic |
| SC-1970 | 52 | 48 | VRT mosaic |
| Loose 1938 (Shinnecock) | 6 | 0 | — |

## Setup

Requires Python 3.11+ and GDAL command-line tools (`brew install gdal`) for the
optional overview step.

```sh
cp .env.example .env          # adjust DATA_ROOT if needed
make setup                    # create .venv and install dependencies
make catalog                  # build data/catalog.json + data/footprints.geojson
make thumbnails               # pre-generate cache/thumbs/ (optional but recommended)
make overviews                # local mosaic overviews for fast map tiles (slow, one-time)
make serve                    # run at http://127.0.0.1:5050
```

`make overviews` copies each survey VRT into `cache/mosaics/` and builds
external overviews there (the data volume is never modified). Without it the
map imagery still works, but zoomed-out tiles take tens of seconds each; with
it they render quickly. The high-res SC-1938-ASA mosaic (~36 GB of sources)
can take an hour or more over USB.

## Architecture

- `scripts/build_catalog.py` — walks every item folder, parses
  `metadata.json`, reads georeferenced raster bounds (header-only) for the
  frames referenced by each survey's VRT, joins ASA town names from
  `registration_report.csv`, and emits `data/catalog.json` +
  `data/footprints.geojson`.
- `scripts/build_thumbnails.py` — resizes JPEG previews (Pillow) or does
  decimated TIFF reads (rasterio) into `cache/thumbs/`.
- `app.py` — Flask server: pages, catalog/footprint APIs, cached thumbnail
  serving, and a dynamic XYZ tile endpoint
  (`/tiles/<collection>/<z>/<x>/<y>.png`) rendered with rio-tiler from the
  VRT mosaics.
- Frontend is vanilla JS + Leaflet 1.9 (CDN); all state comes from
  `/api/catalog` and `/api/footprints`.

## Known limitations (proof of concept)

- Footprints are WGS84 bounding boxes of each georeferenced raster, so rotated
  frames appear slightly larger than the true photo footprint.
- Tile rendering is per-request (LRU-cached in memory); a production deployment
  should pre-render tiles (PMTiles/gdal2tiles) or put a cache in front.
- The two survey index sheets (SC-1938 index JPEG, ASA item 722) are not yet
  catalog items.
- Download page links out to Academic Commons; the georeferenced GeoTIFF
  products exist only on the data drive and are not yet downloadable.
