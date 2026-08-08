from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import config

INPUT_JSONL = config.MEDIA_REGISTRY_JSONL
OUTPUT_SUMMARY = config.MEDIA_REGISTRY_SUMMARY_JSON


def load_records(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def extract_date(value: str | None) -> str | None:
    if not value:
        return None
    # ExifTool-style string: YYYY:MM:DD HH:MM:SS+TZ
    return value[:10].replace(":", "-", 2)


def main() -> None:
    records = load_records(INPUT_JSONL)

    by_extension = Counter()
    by_timestamp_source = Counter()
    by_date = Counter()

    embedded_count = 0
    filesystem_only_count = 0
    gps_count = 0
    camera_count = 0

    hash_groups: dict[str, list[str]] = defaultdict(list)

    for r in records:
        by_extension[r["extension"]] += 1

        exif = r.get("exif", {})
        quality = r.get("metadata_quality", {})

        source = exif.get("created_at_source") or "missing"
        by_timestamp_source[source] += 1

        date_key = extract_date(exif.get("created_at"))
        if date_key:
            by_date[date_key] += 1
        else:
            by_date["missing"] += 1

        if quality.get("has_embedded_capture_time"):
            embedded_count += 1
        else:
            filesystem_only_count += 1

        if quality.get("has_gps"):
            gps_count += 1

        if quality.get("has_camera_metadata"):
            camera_count += 1

        hash_groups[r["hash_sha256"]].append(r["file_path"])

    duplicate_groups = {
        h: paths for h, paths in hash_groups.items() if len(paths) > 1
    }

    summary = {
        "total_files": len(records),
        "extensions": dict(by_extension),
        "timestamp_sources": dict(by_timestamp_source),
        "metadata_quality": {
            "embedded_capture_time_count": embedded_count,
            "filesystem_only_count": filesystem_only_count,
            "gps_count": gps_count,
            "camera_metadata_count": camera_count,
        },
        "dates": dict(sorted(by_date.items())),
        "duplicate_hash_group_count": len(duplicate_groups),
        "duplicate_hash_groups": duplicate_groups,
    }

    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_SUMMARY.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()