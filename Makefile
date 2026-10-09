.PHONY: setup catalog thumbnails overviews overviews-fine all serve serve-prod clean

VENV = .venv/bin
-include .env
DATA_ROOT ?= /path/to/LI-Aerial-Photography
COMMONS = $(DATA_ROOT)/from_digital_commons

setup:
	python3 -m venv .venv
	$(VENV)/pip install -r requirements.txt

catalog:
	$(VENV)/python scripts/build_catalog.py

thumbnails:
	$(VENV)/python scripts/build_thumbnails.py

# Local VRT copies + external overviews make zoomed-out dynamic tiles fast.
# Everything is written under cache/mosaics/ — the data volume stays read-only.
# Levels start at 8: mid-zoom tiles read the base rasters directly (only a few
# frames each), while zoomed-out tiles use the compact overviews. DEFLATE keeps
# the .ovr files small enough for a laptop disk.
OVR_OPTS = --config COMPRESS_OVERVIEW DEFLATE --config PREDICTOR_OVERVIEW 2 --config BIGTIFF_OVERVIEW IF_SAFER

overviews:
	mkdir -p cache/mosaics
	gdal_translate -q -of VRT "$(COMMONS)/Suffolk_County/SC-1938/SC-1938.vrt" cache/mosaics/SC-1938.vrt
	gdal_translate -q -of VRT "$(COMMONS)/Suffolk_County/SC-1947/SC-1947_mosaic.vrt" cache/mosaics/SC-1947.vrt
	gdal_translate -q -of VRT "$(COMMONS)/Suffolk_County/SC-1970/SC-1970_mosaic.vrt" cache/mosaics/SC-1970.vrt
	gdal_translate -q -of VRT "$(COMMONS)/Suffolk_County/SC-1938-ASA/1938_highres_mosaic.vrt" cache/mosaics/SC-1938-ASA.vrt
	gdaladdo -ro $(OVR_OPTS) cache/mosaics/SC-1970.vrt 8 32
	gdaladdo -ro $(OVR_OPTS) cache/mosaics/SC-1947.vrt 8 32 128
	gdaladdo -ro $(OVR_OPTS) cache/mosaics/SC-1938.vrt 8 32 128
	gdaladdo -ro $(OVR_OPTS) cache/mosaics/SC-1938-ASA.vrt 8 32 128

# Finer levels (2, 4) append to the existing .ovr files and close the mid-zoom
# gap (z14-16) where tiles otherwise fall back to slow base-raster reads.
# Run after `overviews`; ~30-60 min over USB, several GB of output.
overviews-fine:
	gdaladdo -ro $(OVR_OPTS) cache/mosaics/SC-1970.vrt 2 4
	gdaladdo -ro $(OVR_OPTS) cache/mosaics/SC-1947.vrt 2 4
	gdaladdo -ro $(OVR_OPTS) cache/mosaics/SC-1938.vrt 2 4
	gdaladdo -ro $(OVR_OPTS) cache/mosaics/SC-1938-ASA.vrt 2 4

all: catalog thumbnails

serve:
	$(VENV)/python app.py

# Production server: no debug mode, one worker (the tile-render semaphore is
# per-process), threaded. Put a reverse proxy with HTTPS in front of it.
serve-prod:
	$(VENV)/gunicorn --workers 1 --threads 16 --timeout 120 \
		--bind 127.0.0.1:$${PORT:-5050} app:app

clean:
	rm -rf data cache
