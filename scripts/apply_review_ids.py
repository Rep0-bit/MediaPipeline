from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REVIEW_CSV = Path(r"C:\Tools\MediaPipeline\pipeline_state\links\multiday_review.csv")
DEFAULT_PLAN_JSONL = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\move_plan_preview.jsonl")
DEFAULT_MANIFEST_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\manifests\review_id_manifest.json")
DEFAULT_MANIFEST_CSV = Path(r"C:\Tools\MediaPipeline\pipeline_state\manifests\review_id_manifest.csv")
DEFAULT_SUMMARY_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\manifests\review_id_summary.json")

SUFFIX_RE = re.compile(r"__REV-(\d{4})$")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_cluster_folder_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cluster_id = row.get("cluster_id")
            proposed_folder = row.get("proposed_folder")
            if cluster_id and proposed_folder and cluster_id not in mapping:
                mapping[cluster_id] = proposed_folder
    return mapping


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "generated_at_utc": None,
            "next_sequence": 1,
            "proposals": {},
        }

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data.setdefault("generated_at_utc", None)
    data.setdefault("next_sequence", 1)
    data.setdefault("proposals", {})
    return data


def save_manifest_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_manifest_csv(path: Path, proposals: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []

    for proposal_id, item in proposals.items():
        rows.append(
            {
                "proposal_id": proposal_id,
                "sequence_no": item.get("sequence_no", ""),
                "label": item.get("label", ""),
                "proposal_type": item.get("proposal_type", ""),
                "confidence": item.get("confidence", ""),
                "suggested_event_name": item.get("suggested_event_name", ""),
                "cluster_ids": ";".join(item.get("cluster_ids", [])),
                "event_days": ";".join(item.get("event_days", [])),
                "applied_folders": ";".join(item.get("applied_folders", [])),
                "last_updated_utc": item.get("last_updated_utc", ""),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "proposal_id",
                "sequence_no",
                "label",
                "proposal_type",
                "confidence",
                "suggested_event_name",
                "cluster_ids",
                "event_days",
                "applied_folders",
                "last_updated_utc",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def split_semicolon(value: str) -> list[str]:
    return [x.strip() for x in (value or "").split(";") if x.strip()]


def strip_review_suffix(name: str) -> str:
    return SUFFIX_RE.sub("", name)


def resolve_current_folder(base_folder: Path) -> Path | None:
    if base_folder.exists() and base_folder.is_dir():
        return base_folder

    parent = base_folder.parent
    stem = base_folder.name

    candidates = sorted([p for p in parent.glob(f"{stem}__REV-*") if p.is_dir()])

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        raise RuntimeError(f"Mais de uma pasta candidata encontrada para {base_folder}: {candidates}")

    return None


def ensure_sequence(manifest: dict[str, Any], proposal_id: str) -> int:
    proposals = manifest["proposals"]

    if proposal_id in proposals and proposals[proposal_id].get("sequence_no"):
        return int(proposals[proposal_id]["sequence_no"])

    seq = int(manifest.get("next_sequence", 1))
    manifest["next_sequence"] = seq + 1

    proposals.setdefault(proposal_id, {})
    proposals[proposal_id]["sequence_no"] = seq
    return seq


def build_label(sequence_no: int) -> str:
    return f"REV-{sequence_no:04d}"


def build_target_folder_name(current_name: str, label: str) -> str:
    base_name = strip_review_suffix(current_name)
    return f"{base_name}__{label}"


def should_mark_row(row: dict[str, str], min_confidence: str) -> bool:
    confidence = (row.get("confidence", "") or "").strip().lower()
    allowed = {"medium", "high"} if min_confidence == "medium" else {"high"}
    return confidence in allowed


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica apenas IDs __REV-xxxx às pastas sugeridas como possível evento multi-dia.")
    parser.add_argument("--review-csv", default=str(DEFAULT_REVIEW_CSV))
    parser.add_argument("--plan-jsonl", default=str(DEFAULT_PLAN_JSONL))
    parser.add_argument("--manifest-json", default=str(DEFAULT_MANIFEST_JSON))
    parser.add_argument("--manifest-csv", default=str(DEFAULT_MANIFEST_CSV))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--execute", action="store_true", help="Executa renomeações. Sem este argumento, corre em dry-run.")
    parser.add_argument("--min-confidence", choices=["medium", "high"], default="medium")
    args = parser.parse_args()

    review_csv = Path(args.review_csv)
    plan_jsonl = Path(args.plan_jsonl)
    manifest_json = Path(args.manifest_json)
    manifest_csv = Path(args.manifest_csv)
    summary_json = Path(args.summary_json)

    review_rows = load_review_rows(review_csv)
    cluster_folder_map = load_cluster_folder_map(plan_jsonl)
    manifest = load_manifest(manifest_json)
    proposals = manifest["proposals"]

    counters: dict[str, int] = {}

    def bump(key: str) -> None:
        counters[key] = counters.get(key, 0) + 1

    for row in review_rows:
        if not should_mark_row(row, args.min_confidence):
            bump("skipped_by_confidence")
            continue

        proposal_id = row.get("proposal_id", "").strip()
        if not proposal_id:
            bump("skipped_missing_proposal_id")
            continue

        cluster_ids = split_semicolon(row.get("cluster_ids", ""))
        event_days = split_semicolon(row.get("event_days", ""))

        if not cluster_ids:
            bump("skipped_missing_cluster_ids")
            continue

        sequence_no = ensure_sequence(manifest, proposal_id)
        label = build_label(sequence_no)

        rename_targets: list[tuple[Path, Path]] = []
        applied_folders: list[str] = []

        for cluster_id in cluster_ids:
            base_folder_str = cluster_folder_map.get(cluster_id)
            if not base_folder_str:
                bump("missing_cluster_folder_mapping")
                continue

            base_folder = Path(base_folder_str)
            current_folder = resolve_current_folder(base_folder)

            if current_folder is None:
                bump("folder_not_found")
                continue

            target_name = build_target_folder_name(current_folder.name, label)
            target_folder = current_folder.with_name(target_name)

            if current_folder == target_folder:
                applied_folders.append(str(current_folder))
                bump("unchanged")
                continue

            if target_folder.exists():
                applied_folders.append(str(target_folder))
                bump("target_exists")
                continue

            rename_targets.append((current_folder, target_folder))

        # deduplicação
        dedup_map: dict[str, tuple[Path, Path]] = {}
        for current_folder, target_folder in rename_targets:
            dedup_map[str(current_folder)] = (current_folder, target_folder)
        rename_targets = list(dedup_map.values())

        for current_folder, target_folder in rename_targets:
            if args.execute:
                current_folder.rename(target_folder)
                applied_folders.append(str(target_folder))
                bump("renamed")
            else:
                applied_folders.append(str(target_folder))
                bump("dry_run_rename")

        proposals.setdefault(proposal_id, {})
        proposals[proposal_id].update(
            {
                "sequence_no": sequence_no,
                "label": label,
                "proposal_type": row.get("proposal_type", ""),
                "confidence": row.get("confidence", ""),
                "suggested_event_name": row.get("suggested_event_name", ""),
                "cluster_ids": cluster_ids,
                "event_days": event_days,
                "applied_folders": applied_folders,
                "last_updated_utc": now_utc(),
            }
        )

    manifest["generated_at_utc"] = now_utc()

    save_manifest_json(manifest_json, manifest)
    save_manifest_csv(manifest_csv, proposals)

    summary = {
        "generated_at_utc": now_utc(),
        "execute": args.execute,
        "review_csv": str(review_csv),
        "plan_jsonl": str(plan_jsonl),
        "manifest_json": str(manifest_json),
        "manifest_csv": str(manifest_csv),
        "min_confidence": args.min_confidence,
        "proposal_count_input": len(review_rows),
        "proposal_count_manifest": len(proposals),
        "result_counters": counters,
    }

    summary_json.parent.mkdir(parents=True, exist_ok=True)
    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Manifest JSON: {manifest_json}")
    print(f"Manifest CSV:  {manifest_csv}")
    print(f"Summary JSON:  {summary_json}")


if __name__ == "__main__":
    main()