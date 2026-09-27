# Разработка

## Требования

- macOS 13 или новее на Apple Silicon для сборки скриптом проекта
- Python 3.12
- Xcode Command Line Tools (для `iconutil`)

## Установка и проверки

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Сборка: `bash scripts/build_macos.sh`. Для изолированной пользовательской проверки используйте `OUTPUT_DIR=previews/build-1.2.0 bash scripts/build_macos.sh`; скрипт не перезаписывает существующий каталог сборки. Тест запускайте с `--data-dir` в отдельной папке. Перед публикацией проверьте приложение. Не включайте в архив профили, базы сессий Telegram, журнал отправок или локальные настройки.
