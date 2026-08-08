from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import config

INPUT_CLUSTERS = config.EVENT_CLUSTER_JSON
INPUT_REGISTRY = config.MEDIA_REGISTRY_ENRICHED_JSONL

TARGET_ROOT = config.ORGANIZED_ROOT

OUTPUT_PLAN_JSON = config.MOVE_PLAN_JSON
OUTPUT_PLAN_JSONL = config.MOVE_PLAN_JSONL
OUTPUT_PLAN_CSV = config.MOVE_PLAN_CSV
OUTPUT_SUMMARY_JSON = config.MOVE_PLAN_SUMMARY_JSON

DOCUMENT_KEYWORDS = {
    "cartão", "cartao", "cidadão", "cidadao", "cc_", "passport", "passaporte",
    "nif", "iban", "invoice", "fatura", "receipt", "recibo", "document", "documento",
    "certificado", "contrato", "apolice", "licença", "licenca", "identidade",
}

INVALID_EVENT_DAYS = {"missing", "0000-00-00"}


def load_clusters(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_registry(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def safe_folder_part(value: str) -> str:
    allowed = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_"):
            allowed.append(ch)
        elif ch == " ":
            allowed.append("_")
    cleaned = "".join(allowed).strip("_")
    return cleaned or "unknown"


def duplicate_penalty(file_name: str) -> tuple[int, int, str]:
    lower = file_name.lower()
    stem = Path(file_name).stem.lower()
    penalty = 0

    if "__dup" in lower:
        penalty += 100
    if " copy" in lower or "_copy" in lower:
        penalty += 50
    if re.search(r" \d+$", stem):
        penalty += 20
    if re.search(r"\(\d+\)$", stem):
        penalty += 20

    return (penalty, len(file_name), lower)


def choose_primary_duplicate(file_records: list[dict[str, Any]]) -> str:
    best = min(file_records, key=lambda r: duplicate_penalty(r["file_name"]))
    return best["file_path"]


def build_duplicate_info(registry_rows: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in registry_rows:
        by_hash[row["hash_sha256"]].append(row)

    primary_by_path: dict[str, str] = {}
    secondary_paths: set[str] = set()

    for _, group in by_hash.items():
        if len(group) <= 1:
            continue
        primary_path = choose_primary_duplicate(group)
        for row in group:
            primary_by_path[row["file_path"]] = primary_path
            if row["file_path"] != primary_path:
                secondary_paths.add(row["file_path"])

    return primary_by_path, secondary_paths


def is_document_file(file_name: str) -> bool:
    lower = file_name.lower()
    return any(keyword in lower for keyword in DOCUMENT_KEYWORDS)


def cluster_day_sequence_map(clusters: list[dict[str, Any]]) -> dict[str, int]:
    per_day_seen: dict[str, list[str]] = defaultdict(list)

    for cluster in clusters:
        event_day = cluster.get("event_day", "missing")
        cluster_id = cluster["cluster_id"]
        if cluster_id not in per_day_seen[event_day]:
            per_day_seen[event_day].append(cluster_id)

    mapping: dict[str, int] = {}
    for _, cluster_ids in per_day_seen.items():
        for idx, cluster_id in enumerate(cluster_ids, start=1):
            mapping[cluster_id] = idx

    return mapping


def cluster_count_per_day(clusters: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter = Counter()
    for cluster in clusters:
        counter[cluster.get("event_day", "missing")] += 1
    return dict(counter)


def should_auto_cluster(cluster: dict[str, Any], day_cluster_count: int) -> bool:
    event_day = cluster.get("event_day", "missing")
    confidence = cluster.get("cluster_confidence", "low")
    file_count = int(cluster.get("file_count", 0))

    if event_day in INVALID_EVENT_DAYS:
        return False

    if confidence == "high":
        return True

    if confidence == "medium" and file_count >= 3 and day_cluster_count == 1:
        return True

    return False


def build_auto_folder(event_day: str, cluster_id: str, cluster_day_seq: dict[str, int]) -> Path:
    year = event_day[:4]
    month_day = event_day[5:]
    seq = cluster_day_seq.get(cluster_id, 1)

    folder_name = month_day if seq == 1 else f"{month_day}_{seq:02d}"
    return TARGET_ROOT / year / folder_name


def propose_destination(folder_root: Path, file_name: str, used_paths: set[str]) -> str:
    candidate = folder_root / file_name
    candidate_key = str(candidate).lower()

    if candidate_key not in used_paths:
        used_paths.add(candidate_key)
        return str(candidate)

    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    counter = 2

    while True:
        candidate = folder_root / f"{stem}__dup{counter:02d}{suffix}"
        candidate_key = str(candidate).lower()
        if candidate_key not in used_paths:
            used_paths.add(candidate_key)
            return str(candidate)
        counter += 1


def main() -> None:
    clusters = load_clusters(INPUT_CLUSTERS)
    registry_rows = load_registry(INPUT_REGISTRY)

    registry_by_path = {row["file_path"]: row for row in registry_rows}
    _, secondary_duplicate_paths = build_duplicate_info(registry_rows)

    day_cluster_counts = cluster_count_per_day(clusters)
    cluster_day_seq = cluster_day_sequence_map(clusters)

    used_destination_paths: set[str] = set()
    move_plan: list[dict[str, Any]] = []

    counters = Counter()

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        event_day = cluster.get("event_day", "missing")
        cluster_confidence = cluster.get("cluster_confidence", "low")
        file_count = int(cluster.get("file_count", 0))
        day_count = day_cluster_counts.get(event_day, 1)

        cluster_auto = should_auto_cluster(cluster, day_count)

        for file_record in cluster.get("files", []):
            file_path = file_record["file_path"]
            file_name = file_record["file_name"]
            registry_row = registry_by_path.get(file_path)

            is_document = is_document_file(file_name)
            is_duplicate_secondary = file_path in secondary_duplicate_paths

            if is_document:
                proposed_bucket = "general"
                proposed_action = "general_document"
                proposed_folder = TARGET_ROOT / "_GENERAL" / "_DOCUMENTS" / safe_folder_part(cluster_id)
            elif is_duplicate_secondary:
                proposed_bucket = "general"
                proposed_action = "general_duplicate"
                proposed_folder = TARGET_ROOT / "_GENERAL" / "_DUPLICATES" / safe_folder_part(cluster_id)
            elif event_day in INVALID_EVENT_DAYS:
                proposed_bucket = "general"
                proposed_action = "general_unsorted"
                proposed_folder = TARGET_ROOT / "_GENERAL" / "_UNSORTED" / safe_folder_part(cluster_id)
            elif cluster_auto:
                proposed_bucket = "auto"
                proposed_action = "auto"
                proposed_folder = build_auto_folder(event_day, cluster_id, cluster_day_seq)
            else:
                proposed_bucket = "review"
                proposed_action = "review"
                proposed_folder = TARGET_ROOT / "_REVIEW" / f"{event_day}_{cluster_id}"

            proposed_destination = propose_destination(
                folder_root=proposed_folder,
                file_name=file_name,
                used_paths=used_destination_paths,
            )

            review_recommended = proposed_bucket == "review"

            row = {
                "cluster_id": cluster_id,
                "event_day": event_day,
                "cluster_confidence": cluster_confidence,
                "cluster_file_count": file_count,
                "day_cluster_count": day_count,
                "review_recommended": review_recommended,
                "proposed_bucket": proposed_bucket,
                "proposed_action": proposed_action,
                "timestamp_start": cluster.get("timestamp_start"),
                "timestamp_end": cluster.get("timestamp_end"),
                "source_path": file_path,
                "proposed_folder": str(proposed_folder),
                "proposed_destination": proposed_destination,
                "file_name": file_name,
                "effective_timestamp": file_record.get("effective_timestamp"),
                "effective_timestamp_source": file_record.get("effective_timestamp_source"),
                "effective_timestamp_confidence": file_record.get("effective_timestamp_confidence"),
                "effective_timestamp_precision": file_record.get("effective_timestamp_precision"),
                "is_document": is_document,
                "is_duplicate_secondary": is_duplicate_secondary,
                "hash_sha256": registry_row.get("hash_sha256") if registry_row else None,
            }

            move_plan.append(row)
            counters[f"bucket_{proposed_bucket}"] += 1
            counters[f"action_{proposed_action}"] += 1

    summary = {
        "total_clusters": len(clusters),
        "total_files": len(move_plan),
        "target_root": str(TARGET_ROOT),
        "result_counters": dict(counters),
        "auto_cluster_count": len({r["cluster_id"] for r in move_plan if r["proposed_bucket"] == "auto"}),
        "review_cluster_count": len({r["cluster_id"] for r in move_plan if r["proposed_bucket"] == "review"}),
        "general_cluster_count": len({r["cluster_id"] for r in move_plan if r["proposed_bucket"] == "general"}),
    }

    OUTPUT_PLAN_JSON.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PLAN_JSON.open("w", encoding="utf-8") as f:
        json.dump(move_plan, f, ensure_ascii=False, indent=2)

    with OUTPUT_PLAN_JSONL.open("w", encoding="utf-8") as f:
        for row in move_plan:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with OUTPUT_SUMMARY_JSON.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with OUTPUT_PLAN_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "cluster_id",
                "event_day",
                "cluster_confidence",
                "cluster_file_count",
                "day_cluster_count",
                "review_recommended",
                "proposed_bucket",
                "proposed_action",
                "timestamp_start",
                "timestamp_end",
                "source_path",
                "proposed_folder",
                "proposed_destination",
                "file_name",
                "effective_timestamp",
                "effective_timestamp_source",
                "effective_timestamp_confidence",
                "effective_timestamp_precision",
                "is_document",
                "is_duplicate_secondary",
                "hash_sha256",
            ],
        )
        writer.writeheader()
        writer.writerows(move_plan)

    print(f"Move plan JSON:   {OUTPUT_PLAN_JSON}")
    print(f"Move plan JSONL:  {OUTPUT_PLAN_JSONL}")
    print(f"Move plan CSV:    {OUTPUT_PLAN_CSV}")
    print(f"Summary JSON:     {OUTPUT_SUMMARY_JSON}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    preview = move_plan[:10]
    print(json.dumps(preview, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()