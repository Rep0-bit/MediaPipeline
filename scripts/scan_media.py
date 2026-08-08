from __future__ import annotations

import hashlib
import json
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

    return {
        "file_path": str(path),
        "file_name": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
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


def main() -> None:
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in SOURCE_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    log(f"Found {len(files)} supported media files in {SOURCE_DIR}")

    with OUTPUT_JSONL.open("w", encoding="utf-8") as out:
        for idx, path in enumerate(files, start=1):
            try:
                record = build_record(path)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                log(f"[{idx}/{len(files)}] Indexed: {path.name}")
            except Exception as exc:
                log(f"[{idx}/{len(files)}] ERROR: {path} | {exc}")

    log(f"Finished. Output written to {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()