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

Baue mit `bash scripts/build_macos.sh`. Für eine isolierte Vorschau nutze `OUTPUT_DIR=previews/build-1.2.0 bash scripts/build_macos.sh`; ein vorhandener Paketordner wird nicht überschrieben. Starte die Vorschau mit `--data-dir` und einem separaten Ordner. Prüfe das App-Bundle vor der Veröffentlichung. Profile, Telegram-Sitzungsdatenbanken, Upload-Journale und lokale Einstellungen gehören nicht ins Archiv.
