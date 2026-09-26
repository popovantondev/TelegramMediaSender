# Entwicklung

## Voraussetzungen

- macOS 13 oder neuer auf Apple Silicon für das bereitgestellte Build-Skript
- Python 3.12
- Xcode Command Line Tools (für `iconutil`)

## Installation und Prüfungen

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Baue mit `bash scripts/build_macos.sh`. Prüfe das App-Bundle vor der Veröffentlichung. Profile, Telegram-Sitzungsdatenbanken und lokale Einstellungen gehören nicht in das Release-Archiv.
