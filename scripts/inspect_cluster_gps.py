from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import config

DEFAULT_CLUSTERS_JSON = config.EVENT_CLUSTER_JSON
DEFAULT_REGISTRY_JSONL = config.MEDIA_REGISTRY_JSONL

def get_lat_lon(source: dict[str, Any]) -> tuple[Any, Any]:
    gps = source.get("exif", {}).get("gps") or {}
    return gps.get("latitude"), gps.get("longitude")


def load_clusters(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            file_path = row.get("file_path")
            if file_path:
                result[file_path] = row
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect one cluster and show files + GPS fields.")
    parser.add_argument("cluster_id")
    parser.add_argument("--clusters", default=str(DEFAULT_CLUSTERS_JSON))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_JSONL))
    parser.add_argument("--max-files", type=int, default=20)
    args = parser.parse_args()

    clusters = load_clusters(Path(args.clusters))
    registry = load_registry(Path(args.registry))

    cluster = next((c for c in clusters if c.get("cluster_id") == args.cluster_id), None)
    if cluster is None:
        raise SystemExit(f"Cluster not found: {args.cluster_id}")

    print(json.dumps(
        {
            "cluster_id": cluster.get("cluster_id"),
            "event_day": cluster.get("event_day"),
            "file_count": cluster.get("file_count"),
            "timestamp_start": cluster.get("timestamp_start"),
            "timestamp_end": cluster.get("timestamp_end"),
        },
        ensure_ascii=False,
        indent=2,
    ))

    print("\nFILES:\n")
    count = 0
    for item in cluster.get("files", []):
        if count >= args.max_files:
            break
        file_path = item.get("file_path")
        reg = registry.get(file_path, {})
        lat, lon = get_lat_lon(reg)
        if lat is None or lon is None:
            lat, lon = get_lat_lon(item)

        print(json.dumps(
            {
                "file_name": item.get("file_name"),
                "file_path": file_path,
                "effective_timestamp": item.get("effective_timestamp") or reg.get("effective_timestamp"),
                "gps_latitude": lat,
                "gps_longitude": lon,
            },
            ensure_ascii=False,
        ))
        count += 1


if __name__ == "__main__":
    main()
