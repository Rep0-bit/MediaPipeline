"""Shared read/append helpers for the organized-tree content-hash index.

The index records the sha256 of every file that has actually been copied or
moved into ORGANIZED_ROOT. build_move_plan_preview.py consults it to avoid
proposing a copy of content that is already backed up somewhere under
organized/, even if that file's cluster_id has since been renumbered or the
file was manually relocated into a hand-named folder.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import config

INDEX_PATH = config.ORGANIZED_HASH_INDEX_JSONL


def load_indexed_hashes(path: Path = INDEX_PATH) -> set[str]:
    if not path.exists():
        return set()

    hashes: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            hashes.add(json.loads(line)["hash_sha256"])
    return hashes


def append_indexed_files(entries: list[dict], path: Path = INDEX_PATH) -> None:
    if not entries:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    with path.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps({**entry, "indexed_at_utc": now}, ensure_ascii=False) + "\n")
