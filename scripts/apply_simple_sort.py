from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INPUT_PLAN = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\move_plan_preview.jsonl")
TARGET_ROOT = Path(r"C:\Tools\Immich\organized")
LOG_FILE = Path(r"C:\Tools\MediaPipeline\pipeline_state\logs\apply_simple_sort.log")
SUMMARY_FILE = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\apply_simple_sort_summary.json")

DRY_RUN = False  # change to True to simulate only


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    line = f"{now_utc()} | {message}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def classify_row(row: dict[str, Any]) -> str:
    confidence = row.get("cluster_confidence", "low")
    review_recommended = bool(row.get("review_recommended", True))
    event_day = row.get("event_day", "missing")

    if confidence == "high" and not review_recommended and event_day != "missing":
        return "auto"

    if review_recommended:
        return "review"

    return "general"


def build_day_sequence_map(rows: list[dict[str, Any]]) -> dict[str, int]:
    """
    Preserves cluster ordering within each day based on first appearance
    in move_plan_preview.jsonl.
    """
    per_day_seen: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        event_day = row.get("event_day", "missing")
        cluster_id = row["cluster_id"]
        if cluster_id not in per_day_seen[event_day]:
            per_day_seen[event_day].append(cluster_id)

    cluster_day_sequence: dict[str, int] = {}
    for event_day, cluster_ids in per_day_seen.items():
        for idx, cluster_id in enumerate(cluster_ids, start=1):
            cluster_day_sequence[cluster_id] = idx

    return cluster_day_sequence


def build_auto_folder(row: dict[str, Any], cluster_day_sequence: dict[str, int]) -> Path:
    event_day = row["event_day"]  # YYYY-MM-DD
    cluster_id = row["cluster_id"]

    year = event_day[:4]
    month_day = event_day[5:]

    seq = cluster_day_sequence.get(cluster_id, 1)
    if seq == 1:
        folder_name = month_day
    else:
        folder_name = f"{month_day}_{seq:02d}"

    return TARGET_ROOT / year / folder_name


def build_destination(row: dict[str, Any], cluster_day_sequence: dict[str, int]) -> Path:
    bucket = classify_row(row)
    file_name = row["file_name"]

    if bucket == "auto":
        return build_auto_folder(row, cluster_day_sequence) / file_name

    if bucket == "review":
        cluster_id = row["cluster_id"]
        event_day = row.get("event_day", "missing")
        return TARGET_ROOT / "_REVIEW" / f"{event_day}_{cluster_id}" / file_name

    return TARGET_ROOT / "_GENERAL" / file_name


def safe_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        try:
            if source.stat().st_size == destination.stat().st_size:
                return "skipped_existing"
        except OSError:
            return "skipped_existing"

        stem = destination.stem
        suffix = destination.suffix
        counter = 2
        while True:
            alt = destination.with_name(f"{stem}__dup{counter:02d}{suffix}")
            if not alt.exists():
                destination = alt
                break
            counter += 1

    if DRY_RUN:
        return f"dry_run -> {destination}"

    shutil.copy2(source, destination)
    return f"copied -> {destination}"


def main() -> None:
    rows = load_rows(INPUT_PLAN)
    cluster_day_sequence = build_day_sequence_map(rows)

    counters = Counter()

    log(f"START | dry_run={DRY_RUN} | rows={len(rows)}")

    for row in rows:
        source = Path(row["source_path"])
        destination = build_destination(row, cluster_day_sequence)
        bucket = classify_row(row)

        counters[f"bucket_{bucket}"] += 1

        if not source.exists():
            counters["source_missing"] += 1
            log(f"SOURCE_MISSING | {source}")
            continue

        result = safe_copy(source, destination)

        if result.startswith("copied"):
            counters["copied"] += 1
        elif result == "skipped_existing":
            counters["skipped_existing"] += 1
        elif result.startswith("dry_run"):
            counters["dry_run_planned"] += 1

        log(f"{bucket.upper()} | {source} | {result}")

    summary = {
        "generated_at_utc": now_utc(),
        "dry_run": DRY_RUN,
        "input_plan": str(INPUT_PLAN),
        "target_root": str(TARGET_ROOT),
        "result_counters": dict(counters),
    }

    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_FILE.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log(f"END | summary_written={SUMMARY_FILE}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()