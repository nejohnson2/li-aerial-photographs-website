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

## Porting to a new machine

The site has three moving parts: this repository (code), the **data volume**
(the LI-Aerial-Photography directory — ~45 GB of scans, read-only), and the
**generated artifacts** (`data/` + `cache/`, rebuildable but slow to rebuild).

### 1. Prerequisites on the new machine

- Python 3.11+
- GDAL command-line tools (`brew install gdal` on macOS,
  `apt install gdal-bin` on Debian/Ubuntu)
- `make`
- Access to the data volume (local disk, or a network mount). For a network
  mount, configure it to mount automatically at boot (fstab/autofs) — the
  server reads from it lazily, so a mount that disappears degrades deep-zoom
  tiles to upscaled overviews until it returns.

### 2. Install

```sh
git clone <this repo> && cd li-aerial-photographs-website
make setup                        # creates .venv, installs pinned deps
cp .env.example .env              # then set DATA_ROOT to the data volume path
```

### 3. Generated artifacts: copy or rebuild

Fastest: copy `data/` and `cache/` from the old machine (rsync/scp). They are
portable **except** `cache/mosaics/*.vrt`, which embed absolute paths to the
data volume. If the volume mounts at a different path on the new machine,
rebuild just the mosaics:

```sh
rm -rf cache/mosaics
make overviews overviews-fine     # ~1-2 h, reads the full archive once
```

(`cache/tiles/`, `cache/thumbs/`, `data/catalog.json`, `data/footprints.geojson`
contain no absolute paths and copy cleanly.)

To rebuild everything from scratch instead:

```sh
make catalog          # ~5 min  — catalog + footprints from metadata/rasters
make thumbnails       # ~15 min — 721 thumbnails
make overviews        # ~30 min — local VRT copies + coarse overviews
make overviews-fine   # ~1 h    — fine levels for fast mid-zoom tiles
```

### 4. Verify

```sh
make serve            # dev server on http://127.0.0.1:5050
```

Check: map shows imagery at low **and** high zoom (high zoom exercises the
data volume), an address search returns frames, and the log shows no
"base rasters unreachable" warnings.

### 5. Exposing to the internet

**Never expose `make serve`** — it runs Flask's debug server, whose
interactive debugger allows remote code execution. For production:

```sh
make serve-prod       # gunicorn on 127.0.0.1:5050, debug off
```

Then put a reverse proxy in front for HTTPS and buffering — e.g. Caddy
(automatic HTTPS):

```
# /etc/caddy/Caddyfile
aerials.example.edu {
    reverse_proxy 127.0.0.1:5050
}
```

or nginx + certbot with a standard `proxy_pass http://127.0.0.1:5050;` block.
Run gunicorn under a process manager (systemd unit, or `launchd` on macOS) so
it restarts on boot; make the unit depend on the data-volume mount.

Notes for public deployment:

- `FLASK_DEBUG` in `.env` only affects `make serve`; gunicorn never enables it.
- The app only reads the data volume and only writes inside `data/` and
  `cache/` — run it as an unprivileged user.
- There are no secrets anywhere in the stack (the Census geocoder needs no
  key); `.env` holds only paths and the port.
- The basemap uses Google's satellite tile endpoint directly, which is not
  formally licensed for third-party sites. For a public deployment consider
  switching the basemap in `static/js/map.js` to Esri World Imagery
  (`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`).
- The first visitors to an area pay the tile-render cost; `cache/tiles/`
  grows and the site gets faster permanently. If you want to pre-warm, browse
  the island at z10–14 once, or script requests against `/tiles/...`.

## Known limitations (proof of concept)

- Footprints are WGS84 bounding boxes of each georeferenced raster, so rotated
  frames appear slightly larger than the true photo footprint.
- Tile rendering is per-request (LRU-cached in memory); a production deployment
  should pre-render tiles (PMTiles/gdal2tiles) or put a cache in front.
- The two survey index sheets (SC-1938 index JPEG, ASA item 722) are not yet
  catalog items.
- Download page links out to Academic Commons; the georeferenced GeoTIFF
  products exist only on the data drive and are not yet downloadable.
