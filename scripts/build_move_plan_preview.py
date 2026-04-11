from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

INPUT_CLUSTERS = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\event_cluster_preview.json")

# Planned organized library root (dry-run only, no files are copied or moved)
TARGET_ROOT = Path(r"C:\Tools\Immich\organized")

OUTPUT_PLAN_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\move_plan_preview.json")
OUTPUT_PLAN_JSONL = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\move_plan_preview.jsonl")
OUTPUT_PLAN_CSV = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\move_plan_preview.csv")
OUTPUT_SUMMARY_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\move_plan_summary.json")


def load_clusters(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_folder_part(value: str) -> str:
    allowed = []
    for ch in value:
        if ch.isalnum() or ch in ("-", "_"):
            allowed.append(ch)
        elif ch in (" ",):
            allowed.append("_")
    cleaned = "".join(allowed).strip("_")
    return cleaned or "unknown"


def folder_name_for_cluster(event_day: str, day_sequence: int) -> tuple[str, str]:
    """
    Returns:
      year_folder: YYYY
      day_folder:  MM-DD or MM-DD_02
    """
    if event_day == "missing":
        year_folder = "unknown"
        base = "unknown-date"
    else:
        year_folder = event_day[:4]
        month_day = event_day[5:]  # MM-DD
        base = month_day

    if day_sequence == 1:
        return year_folder, safe_folder_part(base)

    return year_folder, safe_folder_part(f"{base}_{day_sequence:02d}")


def propose_destination(folder_root: Path, file_name: str, used_paths: set[str]) -> str:
    candidate = folder_root / file_name
    if str(candidate).lower() not in used_paths:
        used_paths.add(str(candidate).lower())
        return str(candidate)

    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    counter = 2

    while True:
        candidate = folder_root / f"{stem}__dup{counter:02d}{suffix}"
        if str(candidate).lower() not in used_paths:
            used_paths.add(str(candidate).lower())
            return str(candidate)
        counter += 1


def review_recommended(cluster: dict[str, Any]) -> bool:
    if cluster.get("cluster_confidence") != "high":
        return True

    for file_record in cluster.get("files", []):
        if file_record.get("effective_timestamp_precision") != "second":
            return True

    return False


def main() -> None:
    clusters = load_clusters(INPUT_CLUSTERS)

    day_sequence_counter: dict[str, int] = defaultdict(int)
    move_plan: list[dict[str, Any]] = []
    used_destination_paths: set[str] = set()

    cluster_count_by_confidence = Counter()
    file_count_by_confidence = Counter()

    for cluster in clusters:
        event_day = cluster.get("event_day", "missing")
        day_sequence_counter[event_day] += 1
        day_sequence = day_sequence_counter[event_day]

        year_folder, day_folder = folder_name_for_cluster(event_day, day_sequence)
        target_folder = TARGET_ROOT / year_folder / day_folder

        cluster_confidence = cluster.get("cluster_confidence", "low")
        cluster_count_by_confidence[cluster_confidence] += 1
        file_count_by_confidence[cluster_confidence] += cluster.get("file_count", 0)

        for file_record in cluster.get("files", []):
            source_path = file_record["file_path"]
            file_name = file_record["file_name"]

            proposed_destination = propose_destination(
                folder_root=target_folder,
                file_name=file_name,
                used_paths=used_destination_paths,
            )

            move_plan.append(
                {
                    "cluster_id": cluster["cluster_id"],
                    "event_day": event_day,
                    "cluster_confidence": cluster_confidence,
                    "review_recommended": review_recommended(cluster),
                    "timestamp_start": cluster.get("timestamp_start"),
                    "timestamp_end": cluster.get("timestamp_end"),
                    "proposed_action": "copy",
                    "source_path": source_path,
                    "proposed_folder": str(target_folder),
                    "proposed_destination": proposed_destination,
                    "file_name": file_name,
                    "effective_timestamp": file_record.get("effective_timestamp"),
                    "effective_timestamp_source": file_record.get("effective_timestamp_source"),
                    "effective_timestamp_confidence": file_record.get("effective_timestamp_confidence"),
                    "effective_timestamp_precision": file_record.get("effective_timestamp_precision"),
                }
            )

    summary = {
        "total_clusters": len(clusters),
        "total_files": len(move_plan),
        "target_root": str(TARGET_ROOT),
        "cluster_count_by_confidence": dict(cluster_count_by_confidence),
        "file_count_by_confidence": dict(file_count_by_confidence),
        "review_recommended_cluster_count": sum(
            1 for cluster in clusters if review_recommended(cluster)
        ),
        "day_sequence_counter": dict(day_sequence_counter),
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
                "review_recommended",
                "timestamp_start",
                "timestamp_end",
                "proposed_action",
                "source_path",
                "proposed_folder",
                "proposed_destination",
                "file_name",
                "effective_timestamp",
                "effective_timestamp_source",
                "effective_timestamp_confidence",
                "effective_timestamp_precision",
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