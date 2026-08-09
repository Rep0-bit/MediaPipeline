from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
import hash_index

DEFAULT_REVIEW_ROOT = config.REVIEW_ROOT
DEFAULT_GENERAL_ROOT = config.GENERAL_ROOT
DEFAULT_CLUSTERS_PATH = config.EVENT_CLUSTER_JSON
DEFAULT_LOG_PATH = config.PROCESS_REVIEW_FOLDERS_LOG
DEFAULT_SUMMARY_PATH = config.PROCESS_REVIEW_FOLDERS_SUMMARY_JSON
DEFAULT_TARGET_ROOT = config.ORGANIZED_ROOT


@dataclass
class Config:
    review_root: Path
    general_root: Path
    clusters_path: Path
    target_root: Path
    log_path: Path
    summary_path: Path
    execute: bool


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_line(path: Path, message: str) -> None:
    line = f"{now_utc()} | {message}"
    print(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_clusters(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


REVIEW_FOLDER_RE = re.compile(
    r"^(?P<event_day>\d{4}-\d{2}-\d{2})_(?P<cluster_id>event-\d+)_(?P<decision>[AG])$"
)


def parse_review_folder_name(folder_name: str) -> tuple[str, str, str, str] | None:
    """Parses the `<event_day>_<cluster_id>_<A|G>` naming produced by
    build_move_plan_preview.py. event_day is read directly from the folder name
    rather than re-derived from cluster_id, because cluster_id is reassigned
    positionally on every cluster_temporal_preview.py run and may no longer
    point at the same (or any) cluster by the time this is executed."""
    match = REVIEW_FOLDER_RE.match(folder_name)
    if not match:
        return None
    event_day = match.group("event_day")
    cluster_id = match.group("cluster_id")
    decision = match.group("decision")
    base_name = f"{event_day}_{cluster_id}"
    return base_name, event_day, cluster_id, decision


def cluster_day_sequence_map(clusters: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, int]]:
    cluster_day: dict[str, str] = {}
    per_day_seen: dict[str, list[str]] = defaultdict(list)

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        event_day = cluster.get("event_day", "missing")
        cluster_day[cluster_id] = event_day
        if cluster_id not in per_day_seen[event_day]:
            per_day_seen[event_day].append(cluster_id)

    cluster_day_seq: dict[str, int] = {}
    for _, cluster_ids in per_day_seen.items():
        for idx, cluster_id in enumerate(cluster_ids, start=1):
            cluster_day_seq[cluster_id] = idx

    return cluster_day, cluster_day_seq


def build_auto_folder(target_root: Path, event_day: str, cluster_id: str, cluster_day_seq: dict[str, int]) -> Path:
    if event_day == "missing":
        return target_root / "_GENERAL" / "_UNSORTED" / cluster_id

    year = event_day[:4]
    month_day = event_day[5:]
    seq = cluster_day_seq.get(cluster_id, 1)

    folder_name = month_day if seq == 1 else f"{month_day}_{seq:02d}"
    return target_root / year / folder_name


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def classify_existing(source: Path, destination: Path) -> str:
    if not destination.exists():
        return "missing"

    try:
        if source.stat().st_size == destination.stat().st_size:
            return "exists_same_size"
        return "exists_conflict"
    except OSError:
        return "exists_unknown"


def resolve_destination_with_suffix(destination: Path) -> Path:
    stem = destination.stem
    suffix = destination.suffix
    counter = 2

    while True:
        alt = destination.with_name(f"{stem}__dup{counter:02d}{suffix}")
        if not alt.exists():
            return alt
        counter += 1


def move_file(source: Path, destination: Path, execute: bool) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)

    existing_status = classify_existing(source, destination)
    if existing_status == "exists_same_size":
        return f"skipped_existing -> {destination}"

    final_destination = destination
    if existing_status in {"exists_conflict", "exists_unknown"}:
        final_destination = resolve_destination_with_suffix(destination)

    if not execute:
        return f"dry_run_move -> {final_destination}"

    shutil.move(str(source), str(final_destination))
    return f"moved -> {final_destination}"


def iter_files(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file()]


def remove_empty_dirs_bottom_up(root: Path, execute: bool) -> list[str]:
    results: list[str] = []
    for folder in sorted([p for p in root.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        try:
            next(folder.iterdir())
        except StopIteration:
            if execute:
                folder.rmdir()
                results.append(f"removed_empty_folder -> {folder}")
            else:
                results.append(f"dry_run_remove_empty_folder -> {folder}")
        except (FileNotFoundError, StopIteration):
            continue

    try:
        next(root.iterdir())
    except StopIteration:
        if execute:
            root.rmdir()
            results.append(f"removed_empty_folder -> {root}")
        else:
            results.append(f"dry_run_remove_empty_folder -> {root}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Processa pastas em _REVIEW terminadas em _A ou _G."
    )
    parser.add_argument("--review-root", default=str(DEFAULT_REVIEW_ROOT))
    parser.add_argument("--general-root", default=str(DEFAULT_GENERAL_ROOT))
    parser.add_argument("--clusters", default=str(DEFAULT_CLUSTERS_PATH))
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY_PATH))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    cfg = Config(
        review_root=Path(args.review_root),
        general_root=Path(args.general_root),
        clusters_path=Path(args.clusters),
        target_root=Path(args.target_root),
        log_path=Path(args.log),
        summary_path=Path(args.summary),
        execute=bool(args.execute),
    )

    if not cfg.review_root.exists():
        raise FileNotFoundError(f"_REVIEW não encontrado: {cfg.review_root}")
    if not cfg.clusters_path.exists():
        raise FileNotFoundError(f"Clusters file não encontrado: {cfg.clusters_path}")

    clusters = load_clusters(cfg.clusters_path)
    cluster_day, cluster_day_seq = cluster_day_sequence_map(clusters)

    counters = Counter()
    decisions_found: list[dict[str, Any]] = []
    newly_indexed: list[dict[str, Any]] = []

    review_dirs = [p for p in cfg.review_root.iterdir() if p.is_dir()]
    log_line(cfg.log_path, f"START | execute={cfg.execute} | review_dirs={len(review_dirs)}")

    for folder in sorted(review_dirs, key=lambda p: p.name.lower()):
        parsed = parse_review_folder_name(folder.name)
        if not parsed:
            counters["ignored_no_suffix"] += 1
            log_line(cfg.log_path, f"IGNORE_NO_SUFFIX | {folder}")
            continue

        base_name, event_day, cluster_id, decision = parsed

        current_cluster_day = cluster_day.get(cluster_id)
        if current_cluster_day is None:
            counters["warn_cluster_id_not_found"] += 1
            log_line(
                cfg.log_path,
                f"WARN_CLUSTER_ID_NOT_FOUND | {folder} | cluster_id={cluster_id} not in current "
                f"{cfg.clusters_path.name} (cluster set was likely regenerated since this review "
                f"folder was created) | proceeding with folder-embedded event_day={event_day}",
            )
        elif current_cluster_day != event_day:
            counters["warn_cluster_day_drift"] += 1
            log_line(
                cfg.log_path,
                f"WARN_CLUSTER_DAY_DRIFT | {folder} | folder_event_day={event_day} | "
                f"cluster_id={cluster_id} now maps to event_day={current_cluster_day} | "
                f"proceeding with folder-embedded event_day={event_day}",
            )

        files = iter_files(folder)

        if decision == "A":
            target_folder = build_auto_folder(cfg.target_root, event_day, cluster_id, cluster_day_seq)
        elif decision == "G":
            target_folder = cfg.general_root / base_name
        else:
            counters["ignored_unknown_decision"] += 1
            log_line(cfg.log_path, f"IGNORE_UNKNOWN_DECISION | {folder}")
            continue

        counters["decision_folders"] += 1
        counters[f"decision_{decision}"] += 1

        decisions_found.append(
            {
                "review_folder": str(folder),
                "base_name": base_name,
                "decision": decision,
                "cluster_id": cluster_id,
                "event_day": event_day,
                "target_folder": str(target_folder),
                "file_count": len(files),
            }
        )

        for source_file in files:
            destination_file = target_folder / source_file.name
            result = move_file(source_file, destination_file, execute=cfg.execute)

            if result.startswith("moved"):
                counters["files_moved"] += 1
                moved_path = Path(result.split(" -> ", 1)[1])
                newly_indexed.append(
                    {
                        "hash_sha256": sha256_file(moved_path),
                        "file_path": str(moved_path),
                        "size_bytes": moved_path.stat().st_size,
                    }
                )
            elif result.startswith("dry_run_move"):
                counters["files_planned"] += 1
            elif result.startswith("skipped_existing"):
                counters["files_skipped_existing"] += 1

            action_name = "APPROVE" if decision == "A" else "GENERAL"
            log_line(cfg.log_path, f"{action_name} | {source_file} | {result}")

        cleanup_results = remove_empty_dirs_bottom_up(folder, execute=cfg.execute)
        for cleanup_result in cleanup_results:
            counters["folder_cleanup_events"] += 1
            log_line(cfg.log_path, f"FOLDER_CLEANUP | {cleanup_result}")

    if cfg.execute:
        hash_index.append_indexed_files(newly_indexed)

    summary = {
        "generated_at_utc": now_utc(),
        "execute": cfg.execute,
        "review_root": str(cfg.review_root),
        "general_root": str(cfg.general_root),
        "clusters_path": str(cfg.clusters_path),
        "result_counters": dict(counters),
        "decisions_found": decisions_found,
    }

    cfg.summary_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg.summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log_line(cfg.log_path, f"END | summary_written={cfg.summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()