#!/bin/bash
# Deploy the Lemma Greek dictionary to a USB-connected Kindle.
#
# Runs the test suite, optionally validates the OPF against Kindle
# Publishing Guidelines via kindling-cli, removes any stale lemma_*
# dictionaries plus FSCK rename artifacts from the device, then copies
# the current lemma_greek_en.mobi from dist/ to documents/dictionaries/
# and ejects the Kindle.
#
# Flags:
#   --skip-tests      Skip the test_dictionary_lookup run.
#   --skip-validate   Skip the kindling-cli manuscript validation step.
#   --no-eject        Don't eject the Kindle after copying.

set -e

KINDLE_DIR="/Volumes/Kindle/documents/dictionaries"
LEMMA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$LEMMA_DIR/dist"
BUILD_DIR="$LEMMA_DIR/lemma_greek_en"
MOBI_NAME="lemma_greek_en.mobi"
OPF_PATH="$BUILD_DIR/lemma_greek_en.opf"
MOBI_SRC="$DIST_DIR/$MOBI_NAME"

SKIP_TESTS=0
SKIP_VALIDATE=0
NO_EJECT=0
for arg in "$@"; do
    case "$arg" in
        --skip-tests)    SKIP_TESTS=1 ;;
        --skip-validate) SKIP_VALIDATE=1 ;;
        --no-eject)      NO_EJECT=1 ;;
        -h|--help)
            sed -n '2,14p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--skip-tests] [--skip-validate] [--no-eject]"
            exit 1
            ;;
    esac
done

if [ ! -f "$MOBI_SRC" ]; then
    echo "Error: $MOBI_SRC not found."
    echo "Build the dictionary first: cd $LEMMA_DIR && ./target/release/lemma -m"
    exit 1
fi

cd "$LEMMA_DIR"

# Run the integration test suite against the current build.
if [ "$SKIP_TESTS" -eq 1 ]; then
    echo "Skipping test_dictionary_lookup (--skip-tests)"
else
    echo "Running test_dictionary_lookup..."
    if [ -x "./target/release/test_dictionary_lookup" ]; then
        ./target/release/test_dictionary_lookup
    else
        cargo run --release --quiet --bin test_dictionary_lookup
    fi
    echo "Tests passed."
fi

# Validate the OPF against Kindle Publishing Guidelines via kindling-cli.
if [ "$SKIP_VALIDATE" -eq 1 ]; then
    echo "Skipping KDP validation (--skip-validate)"
else
    if command -v kindling-cli >/dev/null 2>&1; then
        KINDLING_BIN="$(command -v kindling-cli)"
    elif [ -x "$HOME/Documents/kindling/target/release/kindling-cli" ]; then
        KINDLING_BIN="$HOME/Documents/kindling/target/release/kindling-cli"
    else
        KINDLING_BIN=""
    fi

    if [ -z "$KINDLING_BIN" ]; then
        echo "Warning: kindling-cli not found on PATH or at ~/Documents/kindling/target/release/kindling-cli"
        echo "Skipping validation. Pass --skip-validate to suppress this warning."
    elif [ ! -f "$OPF_PATH" ]; then
        echo "Warning: $OPF_PATH not found, skipping validation."
        echo "(If you only have the .mobi from a GitHub release, run a local build to regenerate the OPF.)"
    else
        echo "Validating $OPF_PATH..."
        "$KINDLING_BIN" validate "$OPF_PATH"
        echo "Validation passed"
    fi
fi

# Check that the Kindle is mounted.
if [ ! -d "$KINDLE_DIR" ]; then
    echo "Error: Kindle not found at $KINDLE_DIR"
    echo "Connect your Kindle via USB and make sure it's mounted."
    exit 1
fi

# Remove stale lemma_* entries and FSCK rename artifacts from the device.
echo "Removing old Lemma dictionaries from Kindle..."
removed=0
while IFS= read -r -d '' f; do
    echo "  deleting $(basename "$f")"
    rm -rf "$f"
    removed=$((removed + 1))
done < <(find "$KINDLE_DIR" -maxdepth 1 \( -name "lemma_*" -o -name "FSCK*" \) -print0 2>/dev/null)

if [ "$removed" -eq 0 ]; then
    echo "  none found"
fi

# Copy the current .mobi over.
echo "Copying $MOBI_NAME to Kindle..."
cp "$MOBI_SRC" "$KINDLE_DIR/"
echo "  copied $(du -h "$MOBI_SRC" | cut -f1)"

if [ "$NO_EJECT" -eq 1 ]; then
    echo "Done. Kindle NOT ejected (--no-eject)."
else
    echo "Ejecting Kindle..."
    cd /  # don't hold the volume
    diskutil eject /Volumes/Kindle
    echo "Done. Safe to unplug."
fi
