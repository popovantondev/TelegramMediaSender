#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -n 1)"
OUTPUT_DIR="${OUTPUT_DIR:-dist}"
STAGE="$OUTPUT_DIR/TelegramMediaSender-$APP_VERSION-macOS-arm64"
PYI_DIST="$OUTPUT_DIR/.pyinstaller"
PYI_WORK="$OUTPUT_DIR/.pyinstaller-work"
BUILD_INFO="$OUTPUT_DIR/build-info.json"
if [[ -e "$STAGE" ]]; then
  echo "Refusing to overwrite existing build: $STAGE" >&2
  exit 1
fi
if [[ -e "$PYI_DIST" || -e "$PYI_WORK" || -e "$BUILD_INFO" ]]; then
  echo "Refusing to overwrite existing build output in: $OUTPUT_DIR" >&2
  exit 1
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info < (3, 12) or sys.version_info >= (3, 14))'; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  fi
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      candidate_path="$(command -v "$candidate")"
      if "$candidate_path" -c 'import sys; raise SystemExit(sys.version_info < (3, 12) or sys.version_info >= (3, 14))'; then
        PYTHON_BIN="$candidate_path"
        break
      fi
    fi
  done
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 12) or sys.version_info >= (3, 14))'; then
  echo "Python 3.12 or 3.13 is required, matching pyproject.toml. Set PYTHON_BIN to a supported executable." >&2
  exit 1
fi
if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e ".[build]"

python scripts/generate_icon.py
mkdir -p "$OUTPUT_DIR"
BUILD_CANDIDATE_ID="${BUILD_CANDIDATE_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
python scripts/write_build_info.py --output "$BUILD_INFO" --candidate "$BUILD_CANDIDATE_ID"
TMS_BUILD_INFO_FILE="$BUILD_INFO" APP_VERSION="$APP_VERSION" pyinstaller --noconfirm --clean \
  --workpath "$PYI_WORK" --distpath "$PYI_DIST" TelegramMediaSender.spec

python scripts/collect_licenses.py
mkdir -p "$STAGE"
cp -R "$PYI_DIST/Telegram Media Sender.app" "$STAGE/"
cp RIGHTS.md THIRD_PARTY_NOTICES.md "$STAGE/"
cp README.md "$STAGE/"
mkdir -p "$STAGE/docs"
mkdir -p "$STAGE/docs/ru"
cp docs/release-check.md "$STAGE/docs/"
cp -R docs/de docs/en docs/images "$STAGE/docs/"
cp docs/ru/README.md docs/ru/telegram-setup.md docs/ru/weekly-uploads.md "$STAGE/docs/ru/"
cp -R build-assets/licenses "$STAGE/Third Party Licenses"
cp "$BUILD_INFO" "$STAGE/build-info.json"
ditto -c -k --sequesterRsrc --keepParent "$STAGE" "$OUTPUT_DIR/TelegramMediaSender-$APP_VERSION-macOS-arm64.zip"
