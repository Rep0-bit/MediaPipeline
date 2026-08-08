from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

import config

DEFAULT_CLUSTERS_JSON = config.EVENT_CLUSTER_JSON
DEFAULT_REGISTRY_JSONL = config.MEDIA_REGISTRY_JSONL
DEFAULT_OUTPUT_PAIRS_JSON = config.MULTIDAY_GPS_PAIRS_JSON
DEFAULT_OUTPUT_REVIEW_CSV = config.MULTIDAY_GPS_REVIEW_CSV
DEFAULT_OUTPUT_SUMMARY_JSON = config.MULTIDAY_GPS_SUMMARY_JSON


def parse_day(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two WGS84 points in metres."""
    earth_radius_m = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


def load_clusters(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return data


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


def get_lat_lon(source: dict[str, Any]) -> tuple[float | None, float | None]:
    gps = source.get("exif", {}).get("gps") or {}
    lat = gps.get("latitude")
    lon = gps.get("longitude")
    if lat is None or lon is None:
        return None, None
    try:
        return float(lat), float(lon)
    except Exception:
        return None, None


def build_cluster_gps_summary(
    clusters: list[dict[str, Any]],
    registry_by_path: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []

    for cluster in clusters:
        gps_points: list[tuple[float, float]] = []

        for item in cluster.get("files", []):
            file_path = item.get("file_path")
            if not file_path:
                continue

            reg_row = registry_by_path.get(file_path, {})
            lat, lon = get_lat_lon(reg_row)

            # Fallback to cluster item fields if registry row does not have GPS.
            if lat is None or lon is None:
                lat, lon = get_lat_lon(item)

            if lat is None or lon is None:
                continue

            gps_points.append((lat, lon))

        latitudes = [p[0] for p in gps_points]
        longitudes = [p[1] for p in gps_points]
        rep_latitude = median(latitudes) if latitudes else None
        rep_longitude = median(longitudes) if longitudes else None

        summaries.append(
            {
                "cluster_id": cluster.get("cluster_id"),
                "event_day": cluster.get("event_day"),
                "file_count": cluster.get("file_count", 0),
                "timestamp_start": cluster.get("timestamp_start"),
                "timestamp_end": cluster.get("timestamp_end"),
                "gps_point_count": len(gps_points),
                "rep_latitude": rep_latitude,
                "rep_longitude": rep_longitude,
            }
        )

    summaries.sort(key=lambda x: (x.get("event_day") or "", x.get("cluster_id") or ""))
    return summaries


def score_pair(
    a: dict[str, Any],
    b: dict[str, Any],
    max_gap_days: int,
    high_distance_m: float,
    medium_distance_m: float,
    min_points_per_cluster: int,
) -> dict[str, Any] | None:
    day_a = parse_day(a["event_day"])
    day_b = parse_day(b["event_day"])
    if day_a is None or day_b is None:
        return None

    gap_days = (day_b - day_a).days
    if gap_days < 1 or gap_days > max_gap_days:
        return None

    if a["rep_latitude"] is None or a["rep_longitude"] is None:
        return None
    if b["rep_latitude"] is None or b["rep_longitude"] is None:
        return None

    if a["gps_point_count"] < min_points_per_cluster or b["gps_point_count"] < min_points_per_cluster:
        return None

    distance_m = haversine_m(
        a["rep_latitude"],
        a["rep_longitude"],
        b["rep_latitude"],
        b["rep_longitude"],
    )

    confidence = None
    notes: list[str] = []

    if gap_days == 1 and distance_m <= high_distance_m:
        confidence = "high"
        notes.append("dias consecutivos")
        notes.append(f"distância <= {high_distance_m:.0f} m")
    elif distance_m <= medium_distance_m:
        confidence = "medium"
        notes.append("dias consecutivos" if gap_days == 1 else "dias próximos")
        notes.append(f"distância <= {medium_distance_m:.0f} m")

    if confidence is None:
        return None

    return {
        "cluster_id_a": a["cluster_id"],
        "event_day_a": a["event_day"],
        "cluster_id_b": b["cluster_id"],
        "event_day_b": b["event_day"],
        "gap_days": gap_days,
        "gps_point_count_a": a["gps_point_count"],
        "gps_point_count_b": b["gps_point_count"],
        "rep_latitude_a": a["rep_latitude"],
        "rep_longitude_a": a["rep_longitude"],
        "rep_latitude_b": b["rep_latitude"],
        "rep_longitude_b": b["rep_longitude"],
        "distance_m": round(distance_m, 1),
        "confidence": confidence,
        "notes": notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Proposes multi-day links using only time proximity and GPS proximity."
    )
    parser.add_argument("--clusters", default=str(DEFAULT_CLUSTERS_JSON))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_JSONL))
    parser.add_argument("--output-pairs", default=str(DEFAULT_OUTPUT_PAIRS_JSON))
    parser.add_argument("--output-review-csv", default=str(DEFAULT_OUTPUT_REVIEW_CSV))
    parser.add_argument("--summary", default=str(DEFAULT_OUTPUT_SUMMARY_JSON))
    parser.add_argument("--max-gap-days", type=int, default=2)
    parser.add_argument("--min-points-per-cluster", type=int, default=1)
    parser.add_argument("--high-distance-m", type=float, default=100.0)
    parser.add_argument("--medium-distance-m", type=float, default=300.0)
    args = parser.parse_args()

    clusters = load_clusters(Path(args.clusters))
    registry_by_path = load_registry(Path(args.registry))
    cluster_summaries = build_cluster_gps_summary(clusters, registry_by_path)

    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(cluster_summaries):
        for b in cluster_summaries[i + 1 :]:
            pair = score_pair(
                a=a,
                b=b,
                max_gap_days=args.max_gap_days,
                high_distance_m=args.high_distance_m,
                medium_distance_m=args.medium_distance_m,
                min_points_per_cluster=args.min_points_per_cluster,
            )
            if pair is not None:
                pairs.append(pair)

    pairs.sort(
        key=lambda x: (
            x["confidence"] != "high",
            x["distance_m"],
            x["gap_days"],
            x["cluster_id_a"],
            x["cluster_id_b"],
        )
    )

    review_rows: list[dict[str, Any]] = []
    for pair in pairs:
        review_rows.append(
            {
                "decision": "",
                "proposal_type": "pair",
                "proposal_id": f'{pair["cluster_id_a"]}__{pair["cluster_id_b"]}',
                "confidence": pair["confidence"],
                "cluster_ids": f'{pair["cluster_id_a"]};{pair["cluster_id_b"]}',
                "event_days": f'{pair["event_day_a"]};{pair["event_day_b"]}',
                "suggested_event_name": "",
                "notes": " | ".join(pair["notes"]) + f' | distance_m={pair["distance_m"]}',
            }
        )

    output_pairs = Path(args.output_pairs)
    output_review_csv = Path(args.output_review_csv)
    output_summary = Path(args.summary)
    output_pairs.parent.mkdir(parents=True, exist_ok=True)

    with output_pairs.open("w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)

    with output_review_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "decision",
                "proposal_type",
                "proposal_id",
                "confidence",
                "cluster_ids",
                "event_days",
                "suggested_event_name",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(review_rows)

    clusters_with_gps = sum(1 for x in cluster_summaries if x["gps_point_count"] > 0)

    summary = {
        "generated_at_utc": datetime.now().isoformat(),
        "input_cluster_count": len(cluster_summaries),
        "clusters_with_gps": clusters_with_gps,
        "candidate_pair_count": len(pairs),
        "high_pair_count": sum(1 for x in pairs if x["confidence"] == "high"),
        "medium_pair_count": sum(1 for x in pairs if x["confidence"] == "medium"),
        "max_gap_days": args.max_gap_days,
        "min_points_per_cluster": args.min_points_per_cluster,
        "high_distance_m": args.high_distance_m,
        "medium_distance_m": args.medium_distance_m,
        "output_pairs": str(output_pairs),
        "output_review_csv": str(output_review_csv),
    }

    with output_summary.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Pairs JSON:   {output_pairs}")
    print(f"Review CSV:   {output_review_csv}")
    print(f"Summary JSON: {output_summary}")


if __name__ == "__main__":
    main()
