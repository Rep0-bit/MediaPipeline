"""Shared paths for MediaPipeline scripts.

Override MEDIAPIPELINE_ROOT / IMMICH_ROOT via environment variables if the
folders ever move or this runs on a different machine.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MEDIAPIPELINE_ROOT = Path(os.environ.get("MEDIAPIPELINE_ROOT", REPO_ROOT))
IMMICH_ROOT = Path(os.environ.get("IMMICH_ROOT", r"C:\Tools\Immich"))

PIPELINE_STATE = MEDIAPIPELINE_ROOT / "pipeline_state"
REGISTRY_DIR = PIPELINE_STATE / "registry"
LOGS_DIR = PIPELINE_STATE / "logs"
LINKS_DIR = PIPELINE_STATE / "links"

SOURCE_PHOTOS_DIR = IMMICH_ROOT / "photos"
ORGANIZED_ROOT = IMMICH_ROOT / "organized"
REVIEW_ROOT = ORGANIZED_ROOT / "_REVIEW"
GENERAL_ROOT = ORGANIZED_ROOT / "_GENERAL"

# Registry files
MEDIA_REGISTRY_JSONL = REGISTRY_DIR / "media_registry.jsonl"
MEDIA_REGISTRY_ENRICHED_JSONL = REGISTRY_DIR / "media_registry_enriched.jsonl"
MEDIA_REGISTRY_SUMMARY_JSON = REGISTRY_DIR / "media_registry_summary.json"
EVENT_CLUSTER_JSON = REGISTRY_DIR / "event_cluster_preview.json"
EVENT_CLUSTER_JSONL = REGISTRY_DIR / "event_cluster_preview.jsonl"
MOVE_PLAN_JSON = REGISTRY_DIR / "move_plan_preview.json"
MOVE_PLAN_JSONL = REGISTRY_DIR / "move_plan_preview.jsonl"
MOVE_PLAN_CSV = REGISTRY_DIR / "move_plan_preview.csv"
MOVE_PLAN_SUMMARY_JSON = REGISTRY_DIR / "move_plan_summary.json"
APPLY_SIMPLE_SORT_SUMMARY_JSON = REGISTRY_DIR / "apply_simple_sort_summary.json"
PROCESS_REVIEW_FOLDERS_SUMMARY_JSON = REGISTRY_DIR / "process_review_folders_summary.json"

# Logs
SCAN_MEDIA_LOG = LOGS_DIR / "scan_media.log"
APPLY_SIMPLE_SORT_LOG = LOGS_DIR / "apply_simple_sort.log"
PROCESS_REVIEW_FOLDERS_LOG = LOGS_DIR / "process_review_folders.log"

# Multi-day GPS linking outputs (experimental, manual use)
MULTIDAY_GPS_PAIRS_JSON = LINKS_DIR / "multiday_gps_candidate_pairs.json"
MULTIDAY_GPS_REVIEW_CSV = LINKS_DIR / "multiday_gps_review.csv"
MULTIDAY_GPS_SUMMARY_JSON = LINKS_DIR / "multiday_gps_summary.json"

# Content-hash index of everything already copied/moved into ORGANIZED_ROOT.
# Used to avoid proposing a copy of a file that has already been backed up,
# regardless of which cluster/folder it lands under on a later rescan.
ORGANIZED_HASH_INDEX_JSONL = REGISTRY_DIR / "organized_hash_index.jsonl"

# --- Experimental Immich-curated workflow (branch experiment/immich-curated-export) ---
# See docs/EXPERIMENTAL_IMMICH_WORKFLOW.md. Both live under IMMICH_ROOT, not
# MEDIAPIPELINE_ROOT, so they can be bind-mounted into the Immich container the
# same way SOURCE_PHOTOS_DIR / ORGANIZED_ROOT already are.
BATCHES_STAGING_ROOT = IMMICH_ROOT / "batches_staging"
ORGANIZED_V2_ROOT = IMMICH_ROOT / "organized_v2"

# Immich REST API base URL. The API key is intentionally NOT read here with a
# default — scripts that need it must read IMMICH_API_KEY from the environment
# themselves and fail clearly if it's unset. Never hardcode or log the key.
IMMICH_API_URL = os.environ.get("IMMICH_API_URL", "http://localhost:2283/api")
