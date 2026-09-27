"""Strict reader for Study Archive Prep publication-plan v1 JSON."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from .weekly_plan import FileCategory, ItemKind, UploadMode, WeeklyPlanItem, WeeklyUploadPlan

FORMAT = "study-archive-publication-plan"
SCHEMA_VERSION = 1
MAX_PLAN_BYTES = 16 * 1024 * 1024


class PublicationPlanImportError(ValueError):
    """The selected publication plan is invalid or unsafe to use."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublicationPlanImportError("The publication plan contains a duplicate JSON key.")
        result[key] = value
    return result


def _uuid(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise PublicationPlanImportError(f"{field} must be a UUID.")
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise PublicationPlanImportError(f"{field} must be a UUID.") from exc
    if parsed != value.lower():
        raise PublicationPlanImportError(f"{field} must use canonical UUID form.")
    return value


def _date(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PublicationPlanImportError(f"{field} must be a date or null.")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise PublicationPlanImportError(f"{field} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise PublicationPlanImportError(f"{field} must use YYYY-MM-DD format.")
    return value


def _file_digest(root: Path, relative: str) -> tuple[Path, int, int, str]:
    """Open each path component relative to a trusted root without following links."""
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        raise PublicationPlanImportError("A file path is empty or uses an unsafe separator.")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise PublicationPlanImportError("A file path must stay inside the selected plan folder.")
    if posix.as_posix() != relative:
        raise PublicationPlanImportError("A file path must use normalized root-relative form.")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    descriptors: list[int] = []
    try:
        root_fd = os.open(root, os.O_RDONLY | directory_flag | nofollow)
        descriptors.append(root_fd)
        parent_fd = root_fd
        for component in posix.parts[:-1]:
            parent_fd = os.open(component, os.O_RDONLY | directory_flag | nofollow, dir_fd=parent_fd)
            descriptors.append(parent_fd)
        file_fd = os.open(posix.parts[-1], os.O_RDONLY | nofollow, dir_fd=parent_fd)
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise PublicationPlanImportError("A publication item must be a regular file.")
        digest = hashlib.sha256()
        with os.fdopen(os.dup(file_fd), "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        after = os.fstat(file_fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise PublicationPlanImportError("A publication item changed while it was being checked.")
        path = root.joinpath(*posix.parts)
        return path, after.st_size, after.st_mtime_ns, digest.hexdigest()
    except PublicationPlanImportError:
        raise
    except OSError as exc:
        raise PublicationPlanImportError(f"A publication file is missing or unsafe: {relative}") from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _keys(item: dict, expected: set[str], label: str) -> None:
    if set(item) != expected:
        raise PublicationPlanImportError(f"{label} has missing or unknown fields.")


def _parse_manifest(data: Any) -> tuple[str, int, list[dict]]:
    if not isinstance(data, dict):
        raise PublicationPlanImportError("The publication plan must be a JSON object.")
    _keys(data, {"format", "schema_version", "project_id", "revision", "items"}, "The publication plan")
    if data["format"] != FORMAT:
        raise PublicationPlanImportError("This file is not a supported publication plan.")
    if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise PublicationPlanImportError("This publication plan version is not supported.")
    project_id = _uuid(data["project_id"], "project_id")
    if type(data["revision"]) is not int or data["revision"] < 1:
        raise PublicationPlanImportError("revision must be a positive integer.")
    if not isinstance(data["items"], list):
        raise PublicationPlanImportError("items must be an ordered list.")
    seen: set[str] = set()
    for position, item in enumerate(data["items"]):
        label = f"items[{position}]"
        if not isinstance(item, dict):
            raise PublicationPlanImportError(f"{label} must be an object.")
        kind = item.get("kind")
        required = ({"id", "kind", "week", "date", "text"} if kind == "text" else
                    {"id", "kind", "week", "date", "path", "name", "size", "sha256"}
                    if kind == "file" else None)
        if required is None:
            raise PublicationPlanImportError(f"{label}.kind must be text or file.")
        _keys(item, required, label)
        item_id = _uuid(item["id"], f"{label}.id")
        if item_id in seen:
            raise PublicationPlanImportError("Publication item IDs must be unique.")
        seen.add(item_id)
        if type(item["week"]) is not int or item["week"] < 1:
            raise PublicationPlanImportError(f"{label}.week must be a positive integer.")
        _date(item["date"], f"{label}.date")
        if kind == "text":
            if not isinstance(item["text"], str) or len(item["text"]) < 1:
                raise PublicationPlanImportError(f"{label}.text must not be empty.")
        else:
            if not isinstance(item["path"], str) or not item["path"]:
                raise PublicationPlanImportError(f"{label}.path must not be empty.")
            if not isinstance(item["name"], str) or not item["name"]:
                raise PublicationPlanImportError(f"{label}.name must not be empty.")
            if type(item["size"]) is not int or item["size"] < 0:
                raise PublicationPlanImportError(f"{label}.size must be a non-negative integer.")
            sha = item["sha256"]
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise PublicationPlanImportError(f"{label}.sha256 must be lowercase hexadecimal SHA-256.")
    return project_id, data["revision"], data["items"]


def load_publication_plan(manifest_path: str | Path) -> WeeklyUploadPlan:
    """Validate a v1 JSON file and every referenced file before returning an immutable plan."""
    source = Path(manifest_path).expanduser()
    selected_parent = source.parent
    try:
        if source.is_symlink() or not source.is_file():
            raise PublicationPlanImportError("The selected publication plan must be a regular, non-symlink file.")
        if selected_parent.is_symlink():
            raise PublicationPlanImportError("The publication plan folder must not be a symbolic link.")
        source = source.resolve(strict=True)
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise PublicationPlanImportError("The selected publication plan must be a regular file.")
            raw = stream.read(MAX_PLAN_BYTES + 1)
        if len(raw) > MAX_PLAN_BYTES:
            raise PublicationPlanImportError("The publication plan is too large.")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except PublicationPlanImportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PublicationPlanImportError("The publication plan is not readable UTF-8 JSON.") from exc
    project_id, revision, entries = _parse_manifest(data)
    root = source.parent.resolve(strict=True)
    if selected_parent.is_symlink() or not root.is_dir():
        raise PublicationPlanImportError("The publication plan folder is not a regular directory.")
    result = []
    for position, entry in enumerate(entries):
        item_id = entry["id"]
        week_key = f"week:{entry['week']}"
        date_value = entry["date"]
        day_key = f"{week_key}/{date_value}" if date_value else None
        if entry["kind"] == "text":
            result.append(WeeklyPlanItem(
                item_id, ItemKind.TEXT, week_key, day_key, None,
                text=entry["text"], position=position,
                group_key=f"publication:{project_id}:{revision}:{week_key}:{day_key or ''}",
                operation_key=item_id))
            continue
        posix = PurePosixPath(entry["path"])
        if posix.name != entry["name"]:
            raise PublicationPlanImportError(f"items[{position}].name must match the path filename.")
        path, size, mtime_ns, digest = _file_digest(root, entry["path"])
        if size != entry["size"]:
            raise PublicationPlanImportError(f"The file size does not match the plan: {entry['path']}")
        if digest != entry["sha256"]:
            raise PublicationPlanImportError(f"The file SHA-256 does not match the plan: {entry['path']}")
        result.append(WeeklyPlanItem(
            item_id, ItemKind.FILE, week_key, day_key, FileCategory.OTHER,
            path=path, relative_path=entry["path"], name=entry["name"],
            size=size, mtime_ns=mtime_ns, sha256=digest, position=position,
            group_key=f"publication:{project_id}:{revision}:{week_key}:{day_key or ''}",
            operation_key=item_id))
    return WeeklyUploadPlan(tuple(result), root,
                            publication_project_id=project_id,
                            publication_revision=revision,
                            mode=UploadMode.PUBLICATION_PLAN)


def revalidate_publication_item(root: Path, relative_path: str,
                                expected_size: int, expected_sha256: str) -> None:
    """Re-check path containment and content immediately before sending an imported file."""
    _, size, _, digest = _file_digest(Path(root).resolve(strict=True), relative_path)
    if size != expected_size or digest != expected_sha256:
        raise PublicationPlanImportError(f"The imported file changed after preview: {relative_path}")
