# Development

## Requirements

- macOS 13 or later on Apple Silicon for the supplied build script
- Python 3.12
- Xcode Command Line Tools (for `iconutil`)

## Setup and checks

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Build with `bash scripts/build_macos.sh`. Inspect the `.app` before publishing; never include profiles, Telegram session databases, or local configuration in a release archive.
