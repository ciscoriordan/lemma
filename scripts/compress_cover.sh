#!/usr/bin/env bash
# Regenerate images/cover.jpg from the hires marketing cover, compressed under
# the 127 KB Kindle Publishing Guidelines limit (KPG section 10.4.2, kindling
# rule R10.4.2a). Re-running is idempotent.
#
# Usage: scripts/compress_cover.sh [source_marketing_cover]
# Default source: ../lemma_pro/covers/lemma_cover_kdp_marketing.jpg

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$REPO_ROOT/../lemma_pro/covers/lemma_cover_kdp_marketing.jpg}"
DST="$REPO_ROOT/images/cover.jpg"
TARGET_WIDTH=1000
TARGET_HEIGHT=1600
QUALITY=85
LIMIT=$((127 * 1024))

if [[ ! -f "$SRC" ]]; then
    echo "Source cover not found: $SRC" >&2
    echo "Pass a path as the first argument or place the marketing cover at the default location." >&2
    exit 1
fi

if ! command -v magick >/dev/null 2>&1; then
    echo "ImageMagick 'magick' binary required. brew install imagemagick" >&2
    exit 1
fi

magick "$SRC" \
    -resize "${TARGET_WIDTH}x${TARGET_HEIGHT}" \
    -strip \
    -interlace Plane \
    -sampling-factor 4:2:0 \
    -quality "$QUALITY" \
    "$DST"

SIZE=$(stat -f%z "$DST" 2>/dev/null || stat -c%s "$DST")
if (( SIZE > LIMIT )); then
    echo "ERROR: compressed cover is $SIZE bytes, over the $LIMIT byte KPG limit" >&2
    echo "Lower QUALITY in $0 and re-run." >&2
    exit 1
fi

printf 'Wrote %s: %d bytes (%dx%d, q=%d)\n' "$DST" "$SIZE" "$TARGET_WIDTH" "$TARGET_HEIGHT" "$QUALITY"
