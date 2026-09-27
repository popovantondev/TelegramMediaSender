"""Crash-safe SQLite journal for weekly Telegram uploads."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import sqlite3
import stat
import time
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .weekly_plan import FileCategory, ItemKind, UploadMode, WeeklyPlanItem, WeeklyUploadPlan


SCHEMA_VERSION = 2
_STATEMENT_TIMEOUT = 15.0


@dataclass(frozen=True)
class FileFingerprint:
    size: int
    mtime_ns: int
    sha256: str


class QueueBusyError(RuntimeError):
    """Another process currently owns this storage's sender queue."""


class FileChangedError(RuntimeError):
    """A file changed while its content fingerprint was being calculated."""


class UncertainReceiptError(RuntimeError):
    """Telegram may have accepted a request but did not return complete receipts."""


class WeeklyJournal:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.data_dir / "weekly_uploads.sqlite3"
        self._lock_handle = None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=_STATEMENT_TIMEOUT)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(f"PRAGMA busy_timeout={int(_STATEMENT_TIMEOUT * 1000)}")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("Weekly upload journal was created by a newer app version.")
            if version == 0:
                db.executescript("""
                    CREATE TABLE runs (
                        run_id INTEGER PRIMARY KEY,
                        profile_id TEXT NOT NULL,
                        account_id INTEGER,
                        chat_id TEXT NOT NULL,
                        chat_title TEXT NOT NULL,
                        root_path TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        state TEXT NOT NULL,
                        plan_json TEXT NOT NULL,
                        mode TEXT NOT NULL DEFAULT 'weekly_study'
                            CHECK(mode IN ('weekly_study','media_groups','publication_plan'))
                    );
                    CREATE TABLE items (
                        item_id INTEGER PRIMARY KEY,
                        run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                        item_key TEXT NOT NULL,
                        position INTEGER NOT NULL,
                        kind TEXT NOT NULL,
                        week_key TEXT NOT NULL,
                        day_key TEXT,
                        category TEXT,
                        relative_path TEXT,
                        text_content TEXT,
                        file_name TEXT,
                        file_size INTEGER NOT NULL DEFAULT 0,
                        mtime_ns INTEGER NOT NULL DEFAULT 0,
                        sha256 TEXT,
                        status TEXT NOT NULL,
                        message_id INTEGER,
                        error TEXT,
                        uncertain INTEGER NOT NULL DEFAULT 0,
                        group_key TEXT,
                        operation_key TEXT,
                        UNIQUE(run_id, item_key, file_size, mtime_ns, sha256)
                    );
                    CREATE INDEX items_run_status ON items(run_id, status, position);
                    CREATE TABLE attempts (
                        attempt_id INTEGER PRIMARY KEY,
                        item_id INTEGER NOT NULL REFERENCES items(item_id),
                        attempt_no INTEGER NOT NULL,
                        random_id INTEGER NOT NULL,
                        started_at REAL NOT NULL,
                        finished_at REAL,
                        result TEXT NOT NULL,
                        message_id INTEGER,
                        error TEXT,
                        operation_key TEXT,
                        UNIQUE(item_id, attempt_no),
                        UNIQUE(random_id)
                    );
                    CREATE TABLE fingerprint_cache (
                        path TEXT NOT NULL,
                        file_size INTEGER NOT NULL,
                        mtime_ns INTEGER NOT NULL,
                        sha256 TEXT NOT NULL,
                        PRIMARY KEY(path, file_size, mtime_ns)
                    );
                    PRAGMA user_version=2;
                """)
            elif version == 1:
                self._backup_before_v2_migration()
                db.execute("BEGIN EXCLUSIVE")
                db.execute("ALTER TABLE runs ADD COLUMN mode TEXT NOT NULL DEFAULT 'weekly_study'")
                db.execute("ALTER TABLE items ADD COLUMN group_key TEXT")
                db.execute("ALTER TABLE items ADD COLUMN operation_key TEXT")
                db.execute("ALTER TABLE attempts ADD COLUMN operation_key TEXT")
                db.execute("UPDATE items SET group_key=COALESCE(day_key,week_key), operation_key=item_key")
                db.execute("PRAGMA user_version=2")
                db.commit()
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _backup_before_v2_migration(self) -> Path:
        """Create a private, consistent SQLite snapshot before adding queue fields."""
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.data_dir, prefix="weekly_uploads-v1-backup-", suffix=".sqlite3")
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with self._connect() as source, sqlite3.connect(temporary) as destination:
                source.backup(destination)
            temporary.chmod(0o600)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return temporary

    @contextmanager
    def executor_lock(self) -> Iterator[None]:
        """Acquire one process-wide execution lease for this data directory."""
        if self._lock_handle is not None:
            raise QueueBusyError("This process already owns the weekly sender queue.")
        lock_path = self.data_dir / "weekly_uploads.lock"
        handle = lock_path.open("a+")
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise QueueBusyError("Another app instance is already sending a weekly queue.") from exc
            self._lock_handle = handle
            yield
        finally:
            self._lock_handle = None
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def fingerprint(self, path: Path, *, use_cache: bool = True, block_size: int = 1024 * 1024) -> FileFingerprint:
        path = Path(path)
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or path.is_symlink():
            raise FileChangedError(f"Not a regular local file: {path}")
        key_path = str(path.resolve())
        if use_cache:
            with self._connect() as db:
                row = db.execute("SELECT sha256 FROM fingerprint_cache WHERE path=? AND file_size=? AND mtime_ns=?",
                                 (key_path, before.st_size, before.st_mtime_ns)).fetchone()
            if row:
                return FileFingerprint(before.st_size, before.st_mtime_ns, row["sha256"])
        digest = hashlib.sha256()
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            while chunk := stream.read(block_size):
                digest.update(chunk)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise FileChangedError(f"File changed while reading: {path}")
        fingerprint = FileFingerprint(after.st_size, after.st_mtime_ns, digest.hexdigest())
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO fingerprint_cache(path,file_size,mtime_ns,sha256) VALUES(?,?,?,?)",
                       (key_path, fingerprint.size, fingerprint.mtime_ns, fingerprint.sha256))
        return fingerprint

    def save_plan(self, plan: WeeklyUploadPlan, fingerprints: dict[str, FileFingerprint] | None = None) -> int:
        """Persist a snapshot of a plan; repeated identical saves reuse the run."""
        fingerprints = fingerprints or {}
        now = time.time()
        scope = (plan.profile_id, plan.account_id, str(plan.chat_id or ""), str(plan.root))
        # The immutable queue identity must include content fingerprints, not
        # just size/mtime. Otherwise a same-size replacement with restored
        # timestamps could reuse a previously sent run.
        serialized = _serialize_plan(plan, fingerprints)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT run_id FROM runs WHERE profile_id=? AND account_id IS ?
                               AND chat_id=? AND root_path=? AND plan_json=?
                               ORDER BY updated_at DESC LIMIT 1""", (*scope, serialized)).fetchone()
            if row:
                run_id = row["run_id"]
                existing = db.execute("SELECT item_key,file_size,mtime_ns,sha256,status FROM items WHERE run_id=?",
                                      (run_id,)).fetchall()
                indexed = {(r["item_key"], r["file_size"], r["mtime_ns"], r["sha256"]): r["status"] for r in existing}
            else:
                cursor = db.execute("""INSERT INTO runs(profile_id,account_id,chat_id,chat_title,root_path,
                                  created_at,updated_at,state,plan_json,mode)
                                  VALUES(?,?,?,?,?,?,?,?,?,?)""",
                                    (*scope[:3], plan.chat_title, scope[3], now, now, "pending",
                                     serialized, plan.mode.value))
                run_id = cursor.lastrowid
                indexed = {}
            for item in plan.items:
                fp = fingerprints.get(item.key)
                size = fp.size if fp else item.size
                mtime = fp.mtime_ns if fp else item.mtime_ns
                sha = fp.sha256 if fp else item.sha256
                item_status = indexed.get((item.key, size, mtime, sha), "pending")
                existing_item = db.execute("""SELECT item_id FROM items WHERE run_id=? AND item_key=?
                                              AND file_size=? AND mtime_ns=? AND sha256 IS ? LIMIT 1""",
                                           (run_id, item.key, size, mtime, sha)).fetchone()
                if existing_item:
                    continue
                db.execute("""INSERT INTO items(run_id,item_key,position,kind,week_key,day_key,
                             category,relative_path,text_content,file_name,file_size,mtime_ns,sha256,status,
                             group_key,operation_key)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (run_id, item.key, item.position, item.kind.value, item.week_key, item.day_key,
                            item.category.value if item.category else None, item.relative_path, item.text,
                            item.name, size, mtime, sha, item_status,
                            item.group_key or item.day_key or item.week_key,
                            item.operation_key or item.key))
            db.execute("UPDATE runs SET updated_at=?, plan_json=?,mode=?,state='pending' WHERE run_id=?",
                       (now, serialized, plan.mode.value, run_id))
            db.commit()
        return int(run_id)

    def run_items(self, run_id: int) -> list[sqlite3.Row]:
        with self._connect() as db:
            return list(db.execute("SELECT * FROM items WHERE run_id=? ORDER BY position,item_id", (run_id,)))

    def resume_interrupted(self, run_id: int) -> list[int]:
        """Mark rows left mid-flight by a crash uncertain; return their ids."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT item_id FROM items WHERE run_id=? AND status='sending'", (run_id,)).fetchall()
            ids = [row["item_id"] for row in rows]
            db.execute("UPDATE items SET status='uncertain', uncertain=1 WHERE run_id=? AND status='sending'", (run_id,))
            db.execute("UPDATE runs SET state='paused',updated_at=? WHERE run_id=?", (time.time(), run_id))
            db.commit()
        return ids

    def begin_attempt(self, item_id: int, random_id: int | None = None) -> tuple[int, int]:
        random_id = random_id or secrets.randbits(63) or 1
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            item = db.execute("SELECT status FROM items WHERE item_id=?", (item_id,)).fetchone()
            if item is None:
                raise KeyError(item_id)
            if item["status"] not in {"pending", "error", "uncertain"}:
                raise ValueError(f"Cannot send an item in state {item['status']}.")
            previous = db.execute("SELECT attempt_id,random_id FROM attempts WHERE item_id=? AND result='uncertain' ORDER BY attempt_no DESC LIMIT 1",
                                  (item_id,)).fetchone()
            if previous:
                attempt_id, random_id = previous["attempt_id"], previous["random_id"]
                db.execute("UPDATE attempts SET result='sending',started_at=?,finished_at=NULL,error=NULL WHERE attempt_id=?",
                           (now, attempt_id))
            else:
                attempt_no = db.execute("SELECT COALESCE(MAX(attempt_no),0)+1 FROM attempts WHERE item_id=?",
                                        (item_id,)).fetchone()[0]
                cursor = db.execute("INSERT INTO attempts(item_id,attempt_no,random_id,started_at,result) VALUES(?,?,?,?,?)",
                                    (item_id, attempt_no, random_id, now, "sending"))
                attempt_id = cursor.lastrowid
            db.execute("UPDATE items SET status='sending',uncertain=0,error=NULL WHERE item_id=?", (item_id,))
            db.commit()
        return int(attempt_id), int(random_id)

    def begin_operation(self, item_ids: list[int], operation_key: str) -> list[tuple[int, int]]:
        """Persist request identities for every item in one network operation."""
        if not item_ids or len(set(item_ids)) != len(item_ids):
            raise ValueError("An operation must contain distinct journal items.")
        now = time.time()
        attempts = []
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for item_id in item_ids:
                item = db.execute("SELECT status,operation_key FROM items WHERE item_id=?", (item_id,)).fetchone()
                if item is None:
                    raise KeyError(item_id)
                if item["status"] not in {"pending", "error", "uncertain"}:
                    raise ValueError(f"Cannot send an item in state {item['status']}.")
                if item["operation_key"] != operation_key:
                    raise ValueError("Journal item does not belong to the requested operation.")
                previous = db.execute(
                    "SELECT attempt_id,random_id FROM attempts WHERE item_id=? AND result='uncertain' "
                    "ORDER BY attempt_no DESC LIMIT 1", (item_id,)).fetchone()
                if previous:
                    attempt_id, random_id = previous["attempt_id"], previous["random_id"]
                    db.execute("UPDATE attempts SET result='sending',started_at=?,finished_at=NULL,error=NULL "
                               "WHERE attempt_id=?", (now, attempt_id))
                else:
                    attempt_no = db.execute(
                        "SELECT COALESCE(MAX(attempt_no),0)+1 FROM attempts WHERE item_id=?",
                        (item_id,)).fetchone()[0]
                    random_id = secrets.randbits(63) or 1
                    cursor = db.execute(
                        "INSERT INTO attempts(item_id,attempt_no,random_id,started_at,result,operation_key) "
                        "VALUES(?,?,?,?,?,?)", (item_id, attempt_no, random_id, now, "sending", operation_key))
                    attempt_id = cursor.lastrowid
                db.execute("UPDATE items SET status='sending',uncertain=0,error=NULL WHERE item_id=?", (item_id,))
                attempts.append((int(attempt_id), int(random_id)))
            db.commit()
        return attempts

    def mark_operation_uncertain(self, entries: list[tuple[int, int]], error: str) -> None:
        """Atomically mark all child sends uncertain after a lost operation receipt."""
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for item_id, attempt_id in entries:
                db.execute("UPDATE attempts SET result='uncertain',finished_at=?,error=? WHERE attempt_id=? "
                           "AND item_id=?", (now, error, attempt_id, item_id))
                changed = db.execute("UPDATE items SET status='uncertain',uncertain=1,error=? "
                                     "WHERE item_id=?", (error, item_id)).rowcount
                if not changed:
                    raise KeyError(item_id)
            db.commit()

    def mark_operation_sent(self, entries: list[tuple[int, int, int]]) -> None:
        """Atomically persist complete per-item receipts before advancing the queue."""
        if not entries or any(message_id <= 0 for _, _, message_id in entries):
            raise ValueError("A successful operation requires a receipt for each item.")
        if len({message_id for _, _, message_id in entries}) != len(entries):
            raise ValueError("Telegram returned duplicate message IDs for one operation.")
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for item_id, attempt_id, message_id in entries:
                attempt = db.execute("SELECT 1 FROM attempts WHERE attempt_id=? AND item_id=?",
                                     (attempt_id, item_id)).fetchone()
                if not attempt:
                    raise KeyError(attempt_id)
                db.execute("UPDATE attempts SET result='sent',finished_at=?,message_id=?,error=NULL "
                           "WHERE attempt_id=?", (now, message_id, attempt_id))
                changed = db.execute("UPDATE items SET status='sent',message_id=?,error=NULL,uncertain=0 "
                                     "WHERE item_id=?", (message_id, item_id)).rowcount
                if not changed:
                    raise KeyError(item_id)
            db.commit()

    def mark_sent(self, item_id: int, attempt_id: int, message_id: int) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE attempts SET result='sent',finished_at=?,message_id=?,error=NULL WHERE attempt_id=?",
                       (now, message_id, attempt_id))
            changed = db.execute("UPDATE items SET status='sent',message_id=?,error=NULL,uncertain=0 WHERE item_id=?",
                                 (message_id, item_id)).rowcount
            if not changed:
                raise KeyError(item_id)
            db.commit()

    def mark_uncertain(self, item_id: int, attempt_id: int, error: str) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE attempts SET result='uncertain',finished_at=?,error=? WHERE attempt_id=?",
                       (now, error, attempt_id))
            db.execute("UPDATE items SET status='uncertain',uncertain=1,error=? WHERE item_id=?",
                       (error, item_id))
            db.commit()

    def mark_error(self, item_id: int, attempt_id: int | None, error: str) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE items SET status='error',uncertain=0,error=? WHERE item_id=?", (error, item_id))
            if attempt_id is not None:
                db.execute("UPDATE attempts SET result='error',finished_at=?,error=? WHERE attempt_id=?",
                           (now, error, attempt_id))
            db.commit()

    def mark_status(self, item_id: int, status: str) -> None:
        if status not in {"pending", "skipped", "error", "uncertain"}:
            raise ValueError(status)
        with self._connect() as db:
            db.execute("UPDATE items SET status=?,uncertain=? WHERE item_id=?",
                       (status, int(status == "uncertain"), item_id))

    def mark_found_in_chat(self, item_id: int, message_id: int) -> None:
        """Store a one-to-one chat-history match without claiming hash verification."""
        with self._connect() as db:
            db.execute("UPDATE items SET status='skipped',message_id=?,error='found_in_chat',uncertain=0 WHERE item_id=?",
                       (message_id, item_id))

    def latest_unfinished_plan(self) -> dict | None:
        """Return the most recently used resumable snapshot without starting it."""
        with self._connect() as db:
            row = db.execute("""SELECT run_id,state,plan_json,updated_at FROM runs
                               WHERE state IN ('pending','sending','paused','failed')
                               ORDER BY updated_at DESC LIMIT 1""").fetchone()
            if row is None:
                return None
            counts = db.execute("""SELECT COUNT(*) AS pending,
                                  SUM(CASE WHEN kind='file' THEN 1 ELSE 0 END) AS files,
                                  SUM(CASE WHEN kind='file' THEN file_size ELSE 0 END) AS bytes
                                  FROM items WHERE run_id=? AND status NOT IN ('sent','skipped')""",
                                (row["run_id"],)).fetchone()
        return {
            "run_id": int(row["run_id"]),
            "state": row["state"],
            "updated_at": float(row["updated_at"]),
            "pending": int(counts["pending"] or 0),
            "pending_files": int(counts["files"] or 0),
            "pending_bytes": int(counts["bytes"] or 0),
            "plan": _deserialize_plan(row["plan_json"]),
        }

    def set_run_state(self, run_id: int, state: str) -> None:
        if state not in {"pending", "sending", "paused", "failed", "completed"}:
            raise ValueError(state)
        with self._connect() as db:
            db.execute("UPDATE runs SET state=?,updated_at=? WHERE run_id=?", (state, time.time(), run_id))


def _serialize_plan(plan: WeeklyUploadPlan,
                    fingerprints: dict[str, FileFingerprint] | None = None) -> str:
    fingerprints = fingerprints or {}
    data = {
        "root": str(plan.root), "profile_id": plan.profile_id, "account_id": plan.account_id,
        "chat_id": plan.chat_id, "chat_title": plan.chat_title,
        "publication_project_id": plan.publication_project_id,
        "publication_revision": plan.publication_revision,
        "items": [],
    }
    if plan.mode is not UploadMode.WEEKLY_STUDY:
        data["plan_schema"] = 2
        data["mode"] = plan.mode.value
    for item in plan.items:
        fingerprint = fingerprints.get(item.key)
        row = {"key": item.key, "kind": item.kind.value, "week_key": item.week_key,
               "day_key": item.day_key, "category": item.category.value if item.category else None,
               "text": item.text, "path": str(item.path) if item.path else None,
               "relative_path": item.relative_path, "name": item.name,
               "size": fingerprint.size if fingerprint else item.size,
               "mtime_ns": fingerprint.mtime_ns if fingerprint else item.mtime_ns,
               "sha256": fingerprint.sha256 if fingerprint else item.sha256,
               "position": item.position}
        if item.group_key is not None:
            row["group_key"] = item.group_key
        if item.operation_key is not None:
            row["operation_key"] = item.operation_key
        data["items"].append(row)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _deserialize_plan(serialized: str) -> WeeklyUploadPlan:
    from pathlib import Path

    data = json.loads(serialized)
    items = tuple(WeeklyPlanItem(
        key=row["key"], kind=ItemKind(row["kind"]), week_key=row["week_key"],
        day_key=row.get("day_key"),
        category=FileCategory(row["category"]) if row.get("category") else None,
        text=row.get("text"), path=Path(row["path"]) if row.get("path") else None,
        relative_path=row.get("relative_path"), name=row.get("name"),
        size=int(row.get("size", 0)), mtime_ns=int(row.get("mtime_ns", 0)),
        sha256=row.get("sha256"), position=int(row.get("position", 0)),
        group_key=row.get("group_key"), operation_key=row.get("operation_key"),
    ) for row in data["items"])
    return WeeklyUploadPlan(
        items, Path(data["root"]), data.get("profile_id", ""),
        data.get("account_id"), data.get("chat_id"), data.get("chat_title", ""),
        data.get("publication_project_id", ""), data.get("publication_revision"),
        UploadMode(data.get("mode", UploadMode.WEEKLY_STUDY.value)),
    )
