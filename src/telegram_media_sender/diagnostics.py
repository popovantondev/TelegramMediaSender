"""Small private diagnostics log containing allow-listed, non-personal events."""
from __future__ import annotations

import fcntl
import json
import os
import platform
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .build_info import build_label


_EVENTS = {
    "app.started", "diagnostics.viewed",
    "chat_refresh.started", "chat_refresh.completed", "chat_refresh.cancelled",
    "chat_refresh.failed", "upload.started", "upload.completed",
    "upload.cancelled", "upload.failed",
}
_SAFE_ENUMS = {
    "mode": {"desktop", "media_groups", "weekly_study", "publication_plan"},
    "phase": {"preparing", "reconciling", "uploading", "waiting_network", "waiting_flood"},
    "status": {"immediate", "safe", "completed", "failed", "cancelled"},
    "result": {"success", "error"},
}
_SAFE_COUNTS = {
    "mode", "phase", "status", "error_type", "item_count", "file_count",
    "message_count", "sent_count", "skipped_count", "uncertain_count",
    "scanned_count", "unsupported_count", "retry_count", "duration_ms", "result",
}
_SAFE_COUNTS -= set(_SAFE_ENUMS) | {"error_type", "result"}
_ERROR_TYPE = re.compile(r"^[A-Z][A-Za-z0-9_]{0,63}$")


class DiagnosticLog:
    """Append privacy-safe JSONL events and keep a bounded set of old entries.

    Arbitrary exception messages and arbitrary fields are deliberately never
    serialized: they may contain a path, phone number, chat name or message.
    """

    def __init__(self, data_dir: Path, *, max_bytes: int = 512 * 1024,
                 backup_count: int = 2):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.data_dir / "diagnostics.jsonl"
        self.lock_path = self.data_dir / "diagnostics.lock"
        self.max_bytes = max(1024, int(max_bytes))
        self.backup_count = max(0, int(backup_count))
        self._thread_lock = threading.Lock()

    def record(self, event: str, *, error: BaseException | type[BaseException] | None = None,
               **fields) -> None:
        """Record one event; diagnostic failures never break the main operation."""
        try:
            event_name = event if isinstance(event, str) and event in _EVENTS else "invalid_event"
            safe = {}
            for key, value in fields.items():
                if key in _SAFE_ENUMS:
                    if isinstance(value, str) and value in _SAFE_ENUMS[key]:
                        safe[key] = value
                    continue
                if key == "result":
                    if isinstance(value, str) and value in _SAFE_ENUMS["result"]:
                        safe[key] = value
                    continue
                if key not in _SAFE_COUNTS:
                    continue
                if isinstance(value, bool):
                    safe[key] = value
                elif isinstance(value, int) and 0 <= value <= 10**12:
                    safe[key] = value
            error_type = error if isinstance(error, type) else type(error) if error is not None else None
            entry = {
                "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "application_version": __version__,
                "build": build_label(),
                "platform": sys.platform,
                "macos_version": platform.mac_ver()[0] if sys.platform == "darwin" else "",
                "event": event_name,
            }
            if error_type is not None:
                name = error_type.__name__[:64]
                if _ERROR_TYPE.fullmatch(name):
                    entry["error_type"] = name
            if safe:
                entry["details"] = safe
            payload = (json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            with self._thread_lock:
                nofollow = getattr(os, "O_NOFOLLOW", 0)
                lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | nofollow, 0o600)
                try:
                    os.fchmod(lock_fd, 0o600)
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                    current_size = self.path.stat().st_size if self.path.exists() else 0
                    if current_size and current_size + len(payload) > self.max_bytes:
                        self._rotate()
                    fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | nofollow, 0o600)
                    try:
                        os.fchmod(fd, 0o600)
                        with os.fdopen(fd, "ab", closefd=False) as stream:
                            stream.write(payload)
                            stream.flush()
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                finally:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
        except Exception:
            # Diagnostics must remain best-effort and must not change app state.
            return

    def _rotate(self) -> None:
        backups = [self.data_dir / f"diagnostics.{index}.jsonl"
                   for index in range(1, self.backup_count + 1)]
        if self.path.is_symlink() or any(path.is_symlink() for path in backups):
            raise OSError("Diagnostics log path is not a regular local file.")
        if self.backup_count == 0:
            self.path.unlink(missing_ok=True)
            return
        oldest = self.data_dir / f"diagnostics.{self.backup_count}.jsonl"
        oldest.unlink(missing_ok=True)
        for index in range(self.backup_count - 1, 0, -1):
            source = self.data_dir / f"diagnostics.{index}.jsonl"
            if source.exists():
                os.replace(source, self.data_dir / f"diagnostics.{index + 1}.jsonl")
        if self.path.exists():
            target = self.data_dir / "diagnostics.1.jsonl"
            os.replace(self.path, target)
            target.chmod(0o600)
