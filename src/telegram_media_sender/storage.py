"""Private settings locations and read-only access to the earlier sender build."""
from __future__ import annotations

import os
import sys
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .i18n import tr
from .diagnostics import DiagnosticLog


class SenderStorage:
    def __init__(self, root: Path | None = None, language: str = "en"):
        self.language = language
        if root is not None:
            self.root = Path(root)
            self.legacy_archive_root = None
            self._prepare_root()
            self.diagnostics = DiagnosticLog(self.root)
            return
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home()))
        else:
            base = Path.home() / "Library" / "Application Support"
        legacy = base / "TelegramArchive"
        self.root = base / "TelegramMediaSender"
        self.legacy_archive_root = legacy if legacy.is_dir() and not legacy.is_symlink() else None
        self._prepare_root()
        self.diagnostics = DiagnosticLog(self.root)

    def _prepare_root(self) -> None:
        if self.root.is_symlink():
            raise ValueError(tr("Invalid application data folder.", self.language))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)

    @contextmanager
    def telegram_operation_lock(self) -> Iterator[None]:
        """Serialize every Telegram operation that shares this app data folder."""
        lock_path = self.root / "telegram-operation.lock"
        with lock_path.open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(tr("Another Telegram operation is already running.", self.language)) from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
