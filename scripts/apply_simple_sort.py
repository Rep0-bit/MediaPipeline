from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

DEFAULT_PLAN = config.MOVE_PLAN_JSONL
DEFAULT_LOG = config.APPLY_SIMPLE_SORT_LOG
DEFAULT_SUMMARY = config.APPLY_SIMPLE_SORT_SUMMARY_JSON


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_line(path: Path, message: str) -> None:
    line = f"{now_utc()} | {message}"
    print(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def classify_existing(source: Path, destination: Path) -> str:
    if not destination.exists():
        return "missing"
    try:
        if source.stat().st_size == destination.stat().st_size:
            return "exists_same_size"
        return "exists_conflict"
    except OSError:
        return "exists_unknown"


def resolve_destination(source: Path, destination: Path) -> Path:
    status = classify_existing(source, destination)
    if status == "missing" or status == "exists_same_size":
        return destination

    stem = destination.stem
    suffix = destination.suffix
    counter = 2

    while True:
        alt = destination.with_name(f"{stem}__dup{counter:02d}{suffix}")
        if not alt.exists():
            return alt
        counter += 1


def copy_one(source: Path, destination: Path, execute: bool) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)

    existing_status = classify_existing(source, destination)
    if existing_status == "exists_same_size":
        return f"skipped_existing -> {destination}"

    final_destination = resolve_destination(source, destination)

    if not execute:
        return f"dry_run_copy -> {final_destination}"

    shutil.copy2(source, final_destination)
    return f"copied -> {final_destination}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aplica o move_plan_preview.jsonl. Sem --execute corre em dry-run."
    )
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    log_path = Path(args.log)
    summary_path = Path(args.summary)
    execute = bool(args.execute)

    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    rows = load_rows(plan_path)
    counters = Counter()

    log_line(log_path, f"START | execute={execute} | rows={len(rows)}")

    for row in rows:
        source = Path(row["source_path"])
        destination = Path(row["proposed_destination"])
        action = row.get("proposed_action", "unknown")
        bucket = row.get("proposed_bucket", "unknown")

        counters[f"bucket_{bucket}"] += 1
        counters[f"action_{action}"] += 1

        if not source.exists():
            counters["source_missing"] += 1
            log_line(log_path, f"SOURCE_MISSING | {source}")
            continue

        result = copy_one(source, destination, execute=execute)

        if result.startswith("copied"):
            counters["copied"] += 1
        elif result.startswith("dry_run_copy"):
            counters["dry_run_planned"] += 1
        elif result.startswith("skipped_existing"):
            counters["skipped_existing"] += 1

        log_line(log_path, f"{bucket.upper()} | {action.upper()} | {source} | {result}")

    summary = {
        "generated_at_utc": now_utc(),
        "execute": execute,
        "plan_path": str(plan_path),
        "log_path": str(log_path),
        "result_counters": dict(counters),
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log_line(log_path, f"END | summary_written={summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()