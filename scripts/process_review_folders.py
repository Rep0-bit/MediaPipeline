from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REVIEW_ROOT = Path(r"C:\Tools\Immich\organized\_REVIEW")
DEFAULT_GENERAL_ROOT = Path(r"C:\Tools\Immich\organized\_GENERAL")
DEFAULT_PLAN_PATH = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\move_plan_preview.jsonl")
DEFAULT_LOG_PATH = Path(r"C:\Tools\MediaPipeline\pipeline_state\logs\process_review_folders.log")
DEFAULT_SUMMARY_PATH = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\process_review_folders_summary.json")


@dataclass
class Config:
    review_root: Path
    general_root: Path
    plan_path: Path
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


def load_move_plan(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_cluster_destination_map(rows: list[dict[str, Any]]) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    conflicts: dict[str, set[str]] = {}

    for row in rows:
        cluster_id = row["cluster_id"]
        proposed_folder = row["proposed_folder"]

        if cluster_id not in mapping:
            mapping[cluster_id] = Path(proposed_folder)
            conflicts[cluster_id] = {proposed_folder}
        else:
            conflicts[cluster_id].add(proposed_folder)

    bad = {cid: vals for cid, vals in conflicts.items() if len(vals) > 1}
    if bad:
        raise ValueError(f"Clusters com mais de um proposed_folder: {bad}")

    return mapping


def parse_review_folder_name(folder_name: str) -> tuple[str, str] | None:
    """
    Espera nomes como:
      2025-09-24_event-0007_A
      2025-09-24_event-0007_G
    Retorna:
      (base_name, decision)
    """
    match = re.match(r"^(?P<base>.+)_(?P<decision>[AG])$", folder_name)
    if not match:
        return None
    return match.group("base"), match.group("decision")


def extract_cluster_id(base_name: str) -> str | None:
    match = re.search(r"(event-\d{4})", base_name)
    if not match:
        return None
    return match.group(1)


def classify_existing(source: Path, destination: Path) -> str:
    if not destination.exists():
        return "missing"

    try:
        if source.stat().st_size == destination.stat().st_size:
            return "exists_same_size"
        return "exists_conflict"
    except OSError:
        return "exists_unknown"


def resolve_destination_with_suffix(source: Path, destination: Path) -> Path:
    status = classify_existing(source, destination)
    if status == "missing":
        return destination
    if status == "exists_same_size":
        return destination

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

    final_destination = resolve_destination_with_suffix(source, destination)

    if not execute:
        return f"dry_run_move -> {final_destination}"

    shutil.move(str(source), str(final_destination))
    return f"moved -> {final_destination}"


def remove_folder_if_empty(folder: Path, execute: bool) -> str:
    try:
        next(folder.iterdir())
        return "not_empty"
    except StopIteration:
        if execute:
            folder.rmdir()
            return "removed_empty_folder"
        return "dry_run_remove_empty_folder"
    except FileNotFoundError:
        return "already_missing"


def iter_files(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Processa pastas em _REVIEW terminadas em _A ou _G."
    )
    parser.add_argument("--review-root", default=str(DEFAULT_REVIEW_ROOT))
    parser.add_argument("--general-root", default=str(DEFAULT_GENERAL_ROOT))
    parser.add_argument("--plan", default=str(DEFAULT_PLAN_PATH))
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY_PATH))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Executa movimentos reais. Sem este flag, corre em dry-run.",
    )
    args = parser.parse_args()

    cfg = Config(
        review_root=Path(args.review_root),
        general_root=Path(args.general_root),
        plan_path=Path(args.plan),
        log_path=Path(args.log),
        summary_path=Path(args.summary),
        execute=bool(args.execute),
    )

    if not cfg.review_root.exists():
        raise FileNotFoundError(f"_REVIEW não encontrado: {cfg.review_root}")
    if not cfg.plan_path.exists():
        raise FileNotFoundError(f"Plano não encontrado: {cfg.plan_path}")

    rows = load_move_plan(cfg.plan_path)
    cluster_destination_map = build_cluster_destination_map(rows)

    counters = Counter()
    decisions_found: list[dict[str, Any]] = []

    review_dirs = [p for p in cfg.review_root.iterdir() if p.is_dir()]
    log_line(cfg.log_path, f"START | execute={cfg.execute} | review_dirs={len(review_dirs)}")

    for folder in sorted(review_dirs, key=lambda p: p.name.lower()):
        parsed = parse_review_folder_name(folder.name)
        if not parsed:
            counters["ignored_no_suffix"] += 1
            log_line(cfg.log_path, f"IGNORE_NO_SUFFIX | {folder}")
            continue

        base_name, decision = parsed
        cluster_id = extract_cluster_id(base_name)
        if not cluster_id:
            counters["ignored_no_cluster_id"] += 1
            log_line(cfg.log_path, f"IGNORE_NO_CLUSTER_ID | {folder}")
            continue

        files = iter_files(folder)
        counters["decision_folders"] += 1
        counters[f"decision_{decision}"] += 1

        if decision == "A":
            target_folder = cluster_destination_map.get(cluster_id)
            if target_folder is None:
                counters["approve_missing_plan_target"] += 1
                log_line(cfg.log_path, f"APPROVE_MISSING_TARGET | {folder} | cluster_id={cluster_id}")
                continue
        elif decision == "G":
            target_folder = cfg.general_root / base_name
        else:
            counters["ignored_unknown_decision"] += 1
            log_line(cfg.log_path, f"IGNORE_UNKNOWN_DECISION | {folder}")
            continue

        decision_record = {
            "review_folder": str(folder),
            "base_name": base_name,
            "decision": decision,
            "cluster_id": cluster_id,
            "target_folder": str(target_folder),
            "file_count": len(files),
        }
        decisions_found.append(decision_record)

        for source_file in files:
            destination_file = target_folder / source_file.name
            result = move_file(source_file, destination_file, execute=cfg.execute)

            if result.startswith("moved"):
                counters["files_moved"] += 1
            elif result.startswith("dry_run_move"):
                counters["files_planned"] += 1
            elif result.startswith("skipped_existing"):
                counters["files_skipped_existing"] += 1

            log_line(
                cfg.log_path,
                f"{'APPROVE' if decision == 'A' else 'GENERAL'} | {source_file} | {result}"
            )

        folder_cleanup_result = remove_folder_if_empty(folder, execute=cfg.execute)
        counters[f"folder_cleanup_{folder_cleanup_result}"] += 1
        log_line(cfg.log_path, f"FOLDER_CLEANUP | {folder} | {folder_cleanup_result}")

    summary = {
        "generated_at_utc": now_utc(),
        "execute": cfg.execute,
        "review_root": str(cfg.review_root),
        "general_root": str(cfg.general_root),
        "plan_path": str(cfg.plan_path),
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