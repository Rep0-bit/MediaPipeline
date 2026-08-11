from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

SOURCE_DIR = config.SOURCE_PHOTOS_DIR
OUTPUT_JSONL = config.MEDIA_REGISTRY_JSONL
LOG_FILE = config.SCAN_MEDIA_LOG

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff",
    ".mp4", ".mov", ".avi", ".mkv", ".webm"
}


def log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"{timestamp} | {message}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def run_exiftool(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["exiftool", "-j", "-n", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ExifTool failed")

    data = json.loads(result.stdout)
    if not data:
        return {}
    return data[0]


def first_nonempty(metadata: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, "", []):
            return value
    return None


def normalize_timestamp(metadata: dict[str, Any]) -> dict[str, str | bool | None]:
    for key in [
        "DateTimeOriginal",
        "CreateDate",
        "MediaCreateDate",
        "TrackCreateDate",
        "FileModifyDate",
    ]:
        value = metadata.get(key)
        if value not in (None, "", []):
            return {
                "value": str(value),
                "source": key,
                "is_embedded": key != "FileModifyDate",
            }
    return {
        "value": None,
        "source": None,
        "is_embedded": False,
    }


def extract_camera(metadata: dict[str, Any]) -> str | None:
    make = metadata.get("Make")
    model = metadata.get("Model")
    if make and model:
        return f"{make} {model}".strip()
    return make or model


def extract_gps(metadata: dict[str, Any]) -> dict[str, float] | None:
    lat = metadata.get("GPSLatitude")
    lon = metadata.get("GPSLongitude")
    if lat is None or lon is None:
        return None
    return {"latitude": lat, "longitude": lon}


def build_record(path: Path) -> dict[str, Any]:
    metadata = run_exiftool(path)

    timestamp_info = normalize_timestamp(metadata)
    gps = extract_gps(metadata)
    camera = extract_camera(metadata)
    stat = path.stat()

    return {
        "file_path": str(path),
        "file_name": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime_epoch": int(stat.st_mtime),
        "hash_sha256": sha256_file(path),
        "exif": {
            "created_at": timestamp_info["value"],
            "created_at_source": timestamp_info["source"],
            "created_at_is_embedded": timestamp_info["is_embedded"],
            "camera": camera,
            "gps": gps,
        },
        "metadata_quality": {
            "has_embedded_capture_time": bool(timestamp_info["is_embedded"]),
            "has_camera_metadata": camera is not None,
            "has_gps": gps is not None,
        },
        "raw_exif_keys": sorted(metadata.keys()),
    }


def load_existing_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            records[record["file_path"]] = record
    return records


def is_unchanged(record: dict[str, Any], path: Path) -> bool:
    if "mtime_epoch" not in record:
        return False
    stat = path.stat()
    return record.get("size_bytes") == stat.st_size and record.get("mtime_epoch") == int(stat.st_mtime)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Faz o scan dos ficheiros de media e atualiza o registo. "
        "Por omissão, ficheiros já indexados (mesmo tamanho e mtime) não são "
        "reprocessados — reutiliza-se o registo anterior para esses casos."
    )
    parser.add_argument(
        "--full-rescan",
        action="store_true",
        help="Ignora o cache e reprocessa (ExifTool + hash) todos os ficheiros, mesmo os já indexados.",
    )
    args = parser.parse_args()

    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in SOURCE_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    existing_records = {} if args.full_rescan else load_existing_records(OUTPUT_JSONL)
    removed_count = len(existing_records) - sum(1 for p in files if str(p) in existing_records)

    log(
        f"Found {len(files)} supported media files in {SOURCE_DIR} "
        f"({len(existing_records)} previously indexed, full_rescan={args.full_rescan})"
    )

    reused_count = 0
    new_count = 0
    changed_count = 0
    error_count = 0

    tmp_path = OUTPUT_JSONL.with_suffix(OUTPUT_JSONL.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as out:
        for idx, path in enumerate(files, start=1):
            file_path_str = str(path)
            existing = existing_records.get(file_path_str)

            if existing is not None and is_unchanged(existing, path):
                out.write(json.dumps(existing, ensure_ascii=False) + "\n")
                reused_count += 1
                continue

            try:
                record = build_record(path)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                if existing is None:
                    new_count += 1
                    log(f"[{idx}/{len(files)}] NEW: {path.name}")
                else:
                    changed_count += 1
                    log(f"[{idx}/{len(files)}] CHANGED: {path.name}")
            except Exception as exc:
                error_count += 1
                if existing is not None:
                    out.write(json.dumps(existing, ensure_ascii=False) + "\n")
                    log(f"[{idx}/{len(files)}] ERROR (a manter registo anterior): {path} | {exc}")
                else:
                    log(f"[{idx}/{len(files)}] ERROR: {path} | {exc}")

    os.replace(tmp_path, OUTPUT_JSONL)

    log(
        f"Finished. reused={reused_count} new={new_count} changed={changed_count} "
        f"removed={removed_count} errors={error_count}. Output written to {OUTPUT_JSONL}"
    )


if __name__ == "__main__":
    main()
