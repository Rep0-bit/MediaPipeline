from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config

INPUT_JSONL = config.MEDIA_REGISTRY_JSONL
OUTPUT_ENRICHED_JSONL = config.MEDIA_REGISTRY_ENRICHED_JSONL
OUTPUT_CLUSTER_JSON = config.EVENT_CLUSTER_JSON
OUTPUT_CLUSTER_JSONL = config.EVENT_CLUSTER_JSONL

HIGH_CONF_GAP_HOURS = 4
MEDIUM_CONF_GAP_HOURS = 8
LOW_CONF_GAP_HOURS = 12


@dataclass
class EffectiveTimestamp:
    value: datetime | None
    source: str | None
    confidence: str
    precision: str | None  # "second", "date", or None


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def is_zero_datetime_string(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    return normalized.startswith("0000:00:00") or normalized.startswith("0000-00-00")


def parse_exif_datetime(value: str | None) -> datetime | None:
    if not value or is_zero_datetime_string(value):
        return None

    formats = [
        "%Y:%m:%d %H:%M:%S%z",
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return None


def parse_filename_timestamp(filename: str) -> tuple[datetime | None, str | None]:
    stem = Path(filename).stem

    patterns_datetime = [
        r"(?<!\d)(\d{8})(\d{6})(?!\d)",              # IMG20240718120904
        r"(?<!\d)(\d{8})_(\d{6})(?!\d)",             # IMG_20201023_184331
        r"(?<!\d)(\d{4})-(\d{2})-(\d{2})[-_](\d{2})-(\d{2})-(\d{2})(?!\d)",  # Screenshot_2024-07-19-20-39-21
    ]

    for pattern in patterns_datetime:
        match = re.search(pattern, stem)
        if not match:
            continue

        groups = match.groups()

        try:
            if len(groups) == 2:
                date_part, time_part = groups
                dt = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                return dt, "second"

            if len(groups) == 6:
                yyyy, mm, dd, hh, mi, ss = groups
                dt = datetime(
                    int(yyyy), int(mm), int(dd), int(hh), int(mi), int(ss), tzinfo=timezone.utc
                )
                return dt, "second"
        except ValueError:
            pass

    patterns_date = [
        r"(?<!\d)(\d{8})(?!\d)",                     # IMG-20240718-WA0004
        r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)",    # screenshot names / other exports
    ]

    for pattern in patterns_date:
        match = re.search(pattern, stem)
        if not match:
            continue

        groups = match.groups()
        try:
            if len(groups) == 1:
                dt = datetime.strptime(groups[0], "%Y%m%d").replace(
                    hour=12, minute=0, second=0, tzinfo=timezone.utc
                )
                return dt, "date"

            if len(groups) == 3:
                yyyy, mm, dd = groups
                dt = datetime(int(yyyy), int(mm), int(dd), 12, 0, 0, tzinfo=timezone.utc)
                return dt, "date"
        except ValueError:
            pass

    return None, None


def derive_effective_timestamp(record: dict[str, Any]) -> EffectiveTimestamp:
    exif = record.get("exif", {})
    created_at = exif.get("created_at")
    created_at_source = exif.get("created_at_source")
    created_at_is_embedded = bool(exif.get("created_at_is_embedded"))

    exif_dt = parse_exif_datetime(created_at)

    if exif_dt and created_at_is_embedded:
        return EffectiveTimestamp(
            value=exif_dt,
            source=created_at_source,
            confidence="high",
            precision="second",
        )

    filename_dt, filename_precision = parse_filename_timestamp(record["file_name"])
    if filename_dt and filename_precision == "second":
        return EffectiveTimestamp(
            value=filename_dt,
            source="FilenameDateTime",
            confidence="medium",
            precision="second",
        )

    if filename_dt and filename_precision == "date":
        return EffectiveTimestamp(
            value=filename_dt,
            source="FilenameDate",
            confidence="medium",
            precision="date",
        )

    if exif_dt:
        return EffectiveTimestamp(
            value=exif_dt,
            source=created_at_source,
            confidence="low",
            precision="second",
        )

    return EffectiveTimestamp(
        value=None,
        source=None,
        confidence="low",
        precision=None,
    )


def isoformat_or_none(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def confidence_rank(conf: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(conf, 0)


def choose_gap_hours(prev_conf: str, curr_conf: str) -> int:
    min_rank = min(confidence_rank(prev_conf), confidence_rank(curr_conf))
    if min_rank >= 2:
        return HIGH_CONF_GAP_HOURS
    if min_rank == 1:
        return MEDIUM_CONF_GAP_HOURS
    return LOW_CONF_GAP_HOURS


def derive_event_day(dt: datetime | None) -> str:
    if dt is None:
        return "missing"
    return dt.date().isoformat()


def should_split_cluster(prev: dict[str, Any], curr: dict[str, Any]) -> bool:
    prev_dt = prev["effective_timestamp_dt"]
    curr_dt = curr["effective_timestamp_dt"]

    if prev_dt is None or curr_dt is None:
        return True

    if prev_dt.date() != curr_dt.date():
        return True

    prev_precision = prev["effective_timestamp_precision"]
    curr_precision = curr["effective_timestamp_precision"]

    if prev_precision == "date" or curr_precision == "date":
        return False

    gap = curr_dt - prev_dt
    gap_hours = gap.total_seconds() / 3600.0
    allowed_gap = choose_gap_hours(prev["effective_timestamp_confidence"], curr["effective_timestamp_confidence"])

    return gap_hours > allowed_gap


def cluster_confidence(items: list[dict[str, Any]]) -> str:
    scores = {"high": 1.0, "medium": 0.7, "low": 0.4}
    avg = sum(scores[item["effective_timestamp_confidence"]] for item in items) / len(items)

    if avg >= 0.85:
        return "high"
    if avg >= 0.60:
        return "medium"
    return "low"


def make_cluster_summary(cluster_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    dts = [item["effective_timestamp_dt"] for item in items if item["effective_timestamp_dt"] is not None]
    source_mix = Counter(item["effective_timestamp_source"] or "missing" for item in items)
    confidence_mix = Counter(item["effective_timestamp_confidence"] for item in items)

    if dts:
        start_dt = min(dts)
        end_dt = max(dts)
        day = start_dt.date().isoformat()
    else:
        start_dt = None
        end_dt = None
        day = "missing"

    return {
        "cluster_id": cluster_id,
        "event_day": day,
        "timestamp_start": isoformat_or_none(start_dt),
        "timestamp_end": isoformat_or_none(end_dt),
        "file_count": len(items),
        "cluster_confidence": cluster_confidence(items),
        "timestamp_source_mix": dict(source_mix),
        "timestamp_confidence_mix": dict(confidence_mix),
        "files": [
            {
                "file_name": item["file_name"],
                "file_path": item["file_path"],
                "effective_timestamp": item["effective_timestamp"],
                "effective_timestamp_source": item["effective_timestamp_source"],
                "effective_timestamp_confidence": item["effective_timestamp_confidence"],
                "effective_timestamp_precision": item["effective_timestamp_precision"],
            }
            for item in items
        ],
    }


def main() -> None:
    records = load_records(INPUT_JSONL)

    enriched_records: list[dict[str, Any]] = []
    for record in records:
        eff = derive_effective_timestamp(record)

        enriched = dict(record)
        enriched["effective_timestamp"] = isoformat_or_none(eff.value)
        enriched["effective_timestamp_source"] = eff.source
        enriched["effective_timestamp_confidence"] = eff.confidence
        enriched["effective_timestamp_precision"] = eff.precision
        enriched["effective_timestamp_dt"] = eff.value

        enriched_records.append(enriched)

    enriched_records.sort(
        key=lambda r: (
            derive_event_day(r["effective_timestamp_dt"]),
            r["effective_timestamp_dt"] or datetime.max.replace(tzinfo=timezone.utc),
            r["file_name"].lower(),
        )
    )

    clusters: list[list[dict[str, Any]]] = []
    current_cluster: list[dict[str, Any]] = []

    for record in enriched_records:
        if not current_cluster:
            current_cluster.append(record)
            continue

        previous = current_cluster[-1]
        if should_split_cluster(previous, record):
            clusters.append(current_cluster)
            current_cluster = [record]
        else:
            current_cluster.append(record)

    if current_cluster:
        clusters.append(current_cluster)

    cluster_summaries: list[dict[str, Any]] = []
    for idx, cluster in enumerate(clusters, start=1):
        cluster_id = f"event-{idx:04d}"
        for item in cluster:
            item["cluster_id"] = cluster_id
        cluster_summaries.append(make_cluster_summary(cluster_id, cluster))

    OUTPUT_ENRICHED_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_ENRICHED_JSONL.open("w", encoding="utf-8") as f:
        for record in enriched_records:
            clean_record = dict(record)
            clean_record.pop("effective_timestamp_dt", None)
            f.write(json.dumps(clean_record, ensure_ascii=False) + "\n")

    with OUTPUT_CLUSTER_JSON.open("w", encoding="utf-8") as f:
        json.dump(cluster_summaries, f, ensure_ascii=False, indent=2)

    with OUTPUT_CLUSTER_JSONL.open("w", encoding="utf-8") as f:
        for cluster in cluster_summaries:
            f.write(json.dumps(cluster, ensure_ascii=False) + "\n")

    print(f"Enriched registry written to: {OUTPUT_ENRICHED_JSONL}")
    print(f"Cluster preview written to:   {OUTPUT_CLUSTER_JSON}")
    print(f"Cluster preview JSONL:        {OUTPUT_CLUSTER_JSONL}")
    print(f"Total clusters: {len(cluster_summaries)}")

    preview = [
        {
            "cluster_id": c["cluster_id"],
            "event_day": c["event_day"],
            "file_count": c["file_count"],
            "cluster_confidence": c["cluster_confidence"],
            "timestamp_start": c["timestamp_start"],
            "timestamp_end": c["timestamp_end"],
            "timestamp_source_mix": c["timestamp_source_mix"],
        }
        for c in cluster_summaries[:10]
    ]
    print(json.dumps(preview, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()