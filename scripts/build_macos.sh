#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  fi
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  for candidate in python3.14 python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      candidate_path="$(command -v "$candidate")"
      if "$candidate_path" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
        PYTHON_BIN="$candidate_path"
        break
      fi
    fi
  done
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
  echo "Python 3.12 or newer is required. Set PYTHON_BIN to its executable." >&2
  exit 1
fi
if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .

python scripts/generate_icon.py
python -c 'import shutil; shutil.rmtree("build", ignore_errors=True); shutil.rmtree("dist/Telegram Media Sender.app", ignore_errors=True)'
pyinstaller --noconfirm --clean TelegramMediaSender.spec

python scripts/collect_licenses.py
STAGE="dist/TelegramMediaSender-1.1.2-macOS-arm64"
python -c 'import shutil; shutil.rmtree("'"$STAGE"'", ignore_errors=True)'
mkdir -p "$STAGE"
cp -R "dist/Telegram Media Sender.app" "$STAGE/"
cp RIGHTS.md THIRD_PARTY_NOTICES.md "$STAGE/"
cp README.md "$STAGE/"
cp -R docs "$STAGE/"
cp -R build-assets/licenses "$STAGE/Third Party Licenses"
ditto -c -k --sequesterRsrc --keepParent "$STAGE" "dist/TelegramMediaSender-1.1.2-macOS-arm64.zip"
