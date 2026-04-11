from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PLAN = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\move_plan_preview.jsonl")
DEFAULT_LOG = Path(r"C:\Tools\MediaPipeline\pipeline_state\logs\apply_move_plan.log")
DEFAULT_SUMMARY = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\apply_move_plan_summary.json")

CONFIDENCE_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


@dataclass
class Config:
    plan_path: Path
    log_path: Path
    summary_path: Path
    execute: bool
    min_confidence: str
    only_auto_approved: bool
    cluster_ids: set[str]
    overwrite: bool


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_line(log_path: Path, message: str) -> None:
    line = f"{now_utc()} | {message}"
    print(line)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_plan(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def confidence_ok(value: str, minimum: str) -> bool:
    return CONFIDENCE_RANK.get(value, -1) >= CONFIDENCE_RANK.get(minimum, -1)


def should_process(row: dict[str, Any], cfg: Config) -> bool:
    if not confidence_ok(row.get("cluster_confidence", "low"), cfg.min_confidence):
        return False

    if cfg.only_auto_approved and row.get("review_recommended", True):
        return False

    if cfg.cluster_ids and row.get("cluster_id") not in cfg.cluster_ids:
        return False

    return True


def classify_existing(source: Path, destination: Path) -> str:
    if not destination.exists():
        return "missing"

    try:
        if source.stat().st_size == destination.stat().st_size:
            return "exists_same_size"
        return "exists_conflict"
    except OSError:
        return "exists_unknown"


def copy_one(row: dict[str, Any], cfg: Config, counters: Counter) -> None:
    source = Path(row["source_path"])
    destination = Path(row["proposed_destination"])
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        counters["source_missing"] += 1
        log_line(cfg.log_path, f"SOURCE_MISSING | {source}")
        return

    existing_status = classify_existing(source, destination)

    if existing_status == "exists_same_size" and not cfg.overwrite:
        counters["skipped_existing"] += 1
        log_line(cfg.log_path, f"SKIP_EXISTING | {source} -> {destination}")
        return

    if existing_status == "exists_conflict" and not cfg.overwrite:
        counters["skipped_conflict"] += 1
        log_line(cfg.log_path, f"SKIP_CONFLICT | {source} -> {destination}")
        return

    if cfg.execute:
        try:
            shutil.copy2(source, destination)
            counters["copied"] += 1
            log_line(cfg.log_path, f"COPIED | {source} -> {destination}")
        except Exception as exc:
            counters["copy_error"] += 1
            log_line(cfg.log_path, f"COPY_ERROR | {source} -> {destination} | {exc}")
    else:
        counters["dry_run_planned"] += 1
        log_line(cfg.log_path, f"DRY_RUN_COPY | {source} -> {destination}")


def build_summary(
    cfg: Config,
    selected_rows: list[dict[str, Any]],
    counters: Counter,
) -> dict[str, Any]:
    cluster_counter = Counter(row["cluster_id"] for row in selected_rows)
    confidence_counter = Counter(row.get("cluster_confidence", "unknown") for row in selected_rows)

    return {
        "generated_at_utc": now_utc(),
        "mode": "execute" if cfg.execute else "dry_run",
        "plan_path": str(cfg.plan_path),
        "log_path": str(cfg.log_path),
        "filters": {
            "min_confidence": cfg.min_confidence,
            "only_auto_approved": cfg.only_auto_approved,
            "cluster_ids": sorted(cfg.cluster_ids),
            "overwrite": cfg.overwrite,
        },
        "selected_file_count": len(selected_rows),
        "selected_cluster_count": len(cluster_counter),
        "selected_clusters": dict(cluster_counter),
        "selected_confidence_mix": dict(confidence_counter),
        "result_counters": dict(counters),
    }


def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="Apply the dry-run media copy plan. Default mode is DRY RUN."
    )
    parser.add_argument(
        "--plan",
        default=str(DEFAULT_PLAN),
        help="Path to move_plan_preview.jsonl",
    )
    parser.add_argument(
        "--log",
        default=str(DEFAULT_LOG),
        help="Path to log file",
    )
    parser.add_argument(
        "--summary",
        default=str(DEFAULT_SUMMARY),
        help="Path to summary JSON",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually copy files. Without this flag, the script runs in dry-run mode.",
    )
    parser.add_argument(
        "--min-confidence",
        choices=["low", "medium", "high"],
        default="high",
        help="Minimum cluster confidence to include. Default: high",
    )
    parser.add_argument(
        "--only-auto-approved",
        action="store_true",
        help="Only process rows where review_recommended is false.",
    )
    parser.add_argument(
        "--cluster-id",
        action="append",
        default=[],
        help="Limit processing to specific cluster_id values. Can be used multiple times.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting destination files if they already exist.",
    )

    args = parser.parse_args()

    return Config(
        plan_path=Path(args.plan),
        log_path=Path(args.log),
        summary_path=Path(args.summary),
        execute=bool(args.execute),
        min_confidence=args.min_confidence,
        only_auto_approved=bool(args.only_auto_approved),
        cluster_ids=set(args.cluster_id),
        overwrite=bool(args.overwrite),
    )


def main() -> None:
    cfg = parse_args()

    if not cfg.plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {cfg.plan_path}")

    rows = load_plan(cfg.plan_path)
    selected_rows = [row for row in rows if should_process(row, cfg)]

    counters: Counter = Counter()
    counters["rows_total"] = len(rows)
    counters["rows_selected"] = len(selected_rows)

    log_line(
        cfg.log_path,
        f"START | mode={'execute' if cfg.execute else 'dry_run'} | "
        f"rows_total={len(rows)} | rows_selected={len(selected_rows)} | "
        f"min_confidence={cfg.min_confidence} | only_auto_approved={cfg.only_auto_approved}",
    )

    for row in selected_rows:
        copy_one(row, cfg, counters)

    summary = build_summary(cfg, selected_rows, counters)
    cfg.summary_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg.summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log_line(cfg.log_path, f"END | summary_written={cfg.summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()