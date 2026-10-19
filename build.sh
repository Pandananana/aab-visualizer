#!/bin/sh
# Build kort.html from your own placeringer.html (see tools/README.md).
set -e
cd "$(dirname "$0")"
[ -f placeringer.html ] || { echo "Mangler placeringer.html i $(pwd) – se tools/README.md" >&2; exit 1; }
cd tools
uv run parse.py
uv run geocode.py
uv run build.py
echo "Færdig: åbn kort.html"
