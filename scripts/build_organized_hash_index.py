"""Rebuilds the organized-tree content-hash index from scratch by hashing
every file currently under ORGANIZED_ROOT.

Run this once to seed the index (including any files already sorted or
manually reorganized before this feature existed), and again any time you
manually move or rename files inside organized/ outside of the pipeline
scripts, since those changes aren't otherwise tracked incrementally.

apply_simple_sort.py and process_review_folders.py append to the same index
automatically as they copy/move files, so routine pipeline runs do not need
to rerun this script.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import config

TARGET_ROOT = config.ORGANIZED_ROOT
OUTPUT_INDEX = config.ORGANIZED_HASH_INDEX_JSONL


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    files = [p for p in TARGET_ROOT.rglob("*") if p.is_file()]
    print(f"Hashing {len(files)} files under {TARGET_ROOT} ...")

    OUTPUT_INDEX.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    with OUTPUT_INDEX.open("w", encoding="utf-8") as f:
        for idx, path in enumerate(files, start=1):
            entry = {
                "hash_sha256": sha256_file(path),
                "file_path": str(path),
                "size_bytes": path.stat().st_size,
                "indexed_at_utc": now,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if idx % 500 == 0 or idx == len(files):
                print(f"  {idx}/{len(files)}")

    print(f"Wrote {len(files)} entries to {OUTPUT_INDEX}")


if __name__ == "__main__":
    main()
