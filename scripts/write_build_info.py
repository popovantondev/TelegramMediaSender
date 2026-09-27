#!/usr/bin/env python3
"""Write reproducibility metadata for a local or release app build."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from importlib.metadata import distributions


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (".github", "docs", "scripts", "src", "tests")
ROOT_FILES = (
    "CHANGELOG.md", "README.md", "RIGHTS.md", "THIRD_PARTY_NOTICES.md",
    "TelegramMediaSender.spec", "pyproject.toml", "requirements.txt", "run_app.py",
)


def source_tree_hash() -> str:
    digest = hashlib.sha256()
    files = [ROOT / name for name in ROOT_FILES]
    for root_name in SOURCE_ROOTS:
        root = ROOT / root_name
        if root.exists():
            files.extend(root.rglob("*"))
    for path in sorted(set(files), key=lambda item: item.relative_to(ROOT).as_posix()):
        if (not path.is_file() or path.is_symlink() or "__pycache__" in path.parts
                or any(part.endswith(".egg-info") for part in path.parts)
                or path.name == ".DS_Store" or path.suffix in {".pyc", ".pyo"}):
            continue
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8") + b"\0")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", default=os.environ.get("BUILD_CANDIDATE_ID", "local"))
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout)
    version = next(
        line.split('"')[1]
        for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
        if line.startswith("version = ")
    )
    info = {
        "application": "Telegram Media Sender",
        "version": version,
        "candidate_id": args.candidate,
        "source_commit": commit,
        "source_tree_sha256": source_tree_hash(),
        "source_tree_dirty": dirty,
        "build_environment_packages": sorted({
            f"{dist.metadata['Name']}=={dist.version}"
            for dist in distributions()
            if dist.metadata.get("Name")
        }),
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
