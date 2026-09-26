"""Private local Telegram profiles for the media-group sender."""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote

from .i18n import tr


class SenderProfileStore:
    LEGACY_DEFAULT_ID = uuid.uuid5(uuid.NAMESPACE_URL, "TelegramArchive/default-session").hex

    def __init__(self, app_root: Path, language: str = "en"):
        self.language = language
        self.root = Path(app_root) / "MediaGroupSender"
        if self.root.is_symlink():
            raise ValueError(tr("Invalid Telegram profile folder.", language))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.sessions = self.root / "sessions"
        if self.sessions.is_symlink():
            raise ValueError(tr("Invalid Telegram sessions folder.", language))
        self.sessions.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.sessions.chmod(0o700)
        self.path = self.root / "profiles.json"
        if self.path.is_symlink():
            raise ValueError(tr("Invalid Telegram profiles file.", language))
        self.migration_marker = self.root / ".legacy-migration-complete"

    def load(self) -> list[dict[str, str]]:
        if self.path.is_symlink():
            raise ValueError(tr("Invalid Telegram profiles file.", self.language))
        if not self.path.exists():
            return []
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(tr("Could not read local Telegram profiles.", self.language)) from error
        if not isinstance(rows, list):
            raise ValueError(tr("The local Telegram profiles file is damaged.", self.language))
        profiles = []
        for row in rows:
            if (not isinstance(row, dict) or not re.fullmatch(r"[0-9a-f]{32}", str(row.get("id", "")))
                    or not all(isinstance(row.get(key), str) for key in ("name", "phone", "api_id", "api_hash"))):
                raise ValueError(tr("The local Telegram profiles file is damaged.", self.language))
            profiles.append({key: row[key] for key in ("id", "name", "phone", "api_id", "api_hash")})
        return profiles

    def add(self, name: str, phone: str, api_id: str, api_hash: str) -> dict[str, str]:
        name, phone, api_id, api_hash = (value.strip() for value in (name, phone, api_id, api_hash))
        if not name or not phone or not api_id.isdigit() or not api_hash:
            raise ValueError(tr("Enter a profile name, phone, numeric API ID, and API Hash.", self.language))
        profiles = self.load()
        if any(profile["phone"] == phone for profile in profiles):
            raise ValueError(tr("A profile with this phone number already exists.", self.language))
        profile = {"id": uuid.uuid4().hex, "name": name, "phone": phone,
                   "api_id": api_id, "api_hash": api_hash}
        profiles.append(profile)
        self._write_profiles(profiles)
        return profile

    def _write_profiles(self, profiles: list[dict[str, str]]) -> None:
        if self.path.is_symlink():
            raise ValueError(tr("Invalid Telegram profiles file.", self.language))
        descriptor, temporary = tempfile.mkstemp(dir=self.root, prefix="profiles-", suffix=".tmp")
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(profiles, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def remove_auto_imported_legacy_profile(self) -> None:
        """Hide the former synthetic default without deleting either app's session."""
        profiles = self.load()
        remaining = [row for row in profiles if row["id"] != self.LEGACY_DEFAULT_ID]
        if len(remaining) != len(profiles):
            self._write_profiles(remaining)

    def delete(self, profile_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", profile_id):
            raise ValueError(tr("Invalid Telegram profile session folder.", self.language))
        profiles = self.load()
        remaining = [row for row in profiles if row["id"] != profile_id]
        if len(remaining) == len(profiles):
            raise ValueError(tr("Telegram profile was not found.", self.language))
        directory = self.sessions / profile_id
        self._validate_session_tree(directory)
        self._write_profiles(remaining)
        try:
            if directory.exists():
                shutil.rmtree(directory)
        except OSError as error:
            # Keep the profile in the list so the user can retry deletion.
            self._write_profiles(profiles)
            raise OSError(tr("Could not delete the Telegram profile session.", self.language)) from error

    def _validate_session_tree(self, directory: Path) -> None:
        if self.sessions.is_symlink() or directory.is_symlink():
            raise ValueError(tr("Invalid Telegram profile session folder.", self.language))
        if directory.parent != self.sessions:
            raise ValueError(tr("Invalid Telegram profile session folder.", self.language))
        if not directory.exists():
            return
        if not directory.is_dir():
            raise ValueError(tr("Invalid Telegram profile session folder.", self.language))
        for current, dirs, files in os.walk(directory, followlinks=False):
            for name in dirs + files:
                mode = (Path(current) / name).lstat().st_mode
                if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                    raise ValueError(tr("Invalid Telegram profile session folder.", self.language))

    @staticmethod
    def _sqlite_backup(source: Path, destination: Path) -> None:
        if source.is_symlink() or not source.is_file() or destination.is_symlink():
            raise ValueError("Unsafe SQLite session path")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix="session-", suffix=".tmp")
        os.close(descriptor)
        try:
            with sqlite3.connect(f"file:{quote(str(source))}?mode=ro", uri=True) as old:
                with sqlite3.connect(temporary) as new:
                    old.backup(new)
            os.chmod(temporary, 0o600)
            if not destination.exists():
                os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def migrate_from_legacy(self, archive_root: Path | None) -> None:
        """Import once into the new store without modifying the old application."""
        if archive_root is None or self.migration_marker.exists():
            return
        archive_root = Path(archive_root)
        old_sender = archive_root / "MediaGroupSender"
        old_file = old_sender / "profiles.json"
        if archive_root.is_symlink() or old_sender.is_symlink() or old_file.is_symlink():
            raise ValueError(tr("Invalid Telegram profiles file.", self.language))
        old_rows = []
        if old_file.exists():
            try:
                old_rows = json.loads(old_file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise ValueError(tr("Could not read local Telegram profiles.", self.language)) from error
            if not isinstance(old_rows, list):
                raise ValueError(tr("The local Telegram profiles file is damaged.", self.language))
        profiles = self.load()
        known_ids = {row["id"] for row in profiles}
        known_phones = {row["phone"] for row in profiles if row["phone"]}
        additions = []
        for row in old_rows:
            if (not isinstance(row, dict) or not re.fullmatch(r"[0-9a-f]{32}", str(row.get("id", "")))
                    or not all(isinstance(row.get(key), str) for key in ("name", "phone", "api_id", "api_hash"))):
                raise ValueError(tr("The local Telegram profiles file is damaged.", self.language))
            if row["id"] in known_ids or (row["phone"] and row["phone"] in known_phones):
                continue
            source = old_sender / "sessions" / row["id"] / "telegram.session"
            if source.exists() or source.is_symlink():
                if source.parent.is_symlink() or source.parent.parent.is_symlink():
                    raise ValueError(tr("Invalid Telegram profile session folder.", self.language))
                target = self.session_path(row, self.root)
                self._sqlite_backup(source, target)
            additions.append({key: row[key] for key in ("id", "name", "phone", "api_id", "api_hash")})
            known_ids.add(row["id"])
            if row["phone"]:
                known_phones.add(row["phone"])
        if additions:
            self._write_profiles(profiles + additions)
        # A failed copy or write never marks the migration complete. A later
        # attempt is idempotent and never replaces a session already imported.
        descriptor = os.open(self.migration_marker, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
        os.close(descriptor)

    def session_path(self, profile: dict[str, str], app_root: Path) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", profile["id"]):
            raise ValueError(tr("Invalid Telegram profile session folder.", self.language))
        directory = self.sessions / profile["id"]
        if directory.is_symlink():
            raise ValueError(tr("Invalid Telegram profile session folder.", self.language))
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        path = directory / "telegram.session"
        if path.is_symlink():
            raise ValueError(tr("Invalid Telegram session file.", self.language))
        return path
