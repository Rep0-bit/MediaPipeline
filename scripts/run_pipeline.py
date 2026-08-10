"""Runs the standard MediaPipeline sequence as a single command: scan ->
summarize -> cluster -> build plan -> apply.

Does NOT run process_review_folders.py, since that step requires manually
reviewing and renaming _REVIEW folders first (see docs/GUIA_UTILIZACAO.md,
secção 3) — run it separately once that review is done.

Without --execute, every step runs in preview/dry-run mode (apply_simple_sort.py
defaults to dry-run) so nothing is copied. Pass --execute to actually copy files.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import config

SCRIPTS_DIR = Path(__file__).resolve().parent

STEPS = [
    "scan_media.py",
    "summarize_registry.py",
    "cluster_temporal_preview.py",
    "build_move_plan_preview.py",
    "apply_simple_sort.py",
]


def run_step(script_name: str, extra_args: list[str]) -> None:
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path), *extra_args]

    print(f"\n=== {script_name} {' '.join(extra_args)} ===".rstrip())
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\nFALHOU: {script_name} (exit code {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Corre scan -> summarize -> cluster -> build plan -> apply numa única chamada."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Executa apply_simple_sort.py em modo real (copia ficheiros). "
        "Sem esta flag, tudo corre em preview/dry-run.",
    )
    args = parser.parse_args()

    print(f"MEDIAPIPELINE_ROOT: {config.MEDIAPIPELINE_ROOT}")
    print(f"IMMICH_ROOT:        {config.IMMICH_ROOT}")

    for script_name in STEPS:
        extra_args = ["--execute"] if (script_name == "apply_simple_sort.py" and args.execute) else []
        run_step(script_name, extra_args)

    print("\n=== Concluído ===")
    if args.execute:
        print(
            "Ficheiros copiados. Reveja as pastas em _REVIEW e corra "
            "process_review_folders.py --execute quando terminar a revisão manual."
        )
    else:
        print(
            "Modo preview (sem --execute) — nada foi copiado. Reveja "
            "pipeline_state\\registry\\move_plan_summary.json e volte a correr "
            "com --execute quando estiver pronto."
        )


if __name__ == "__main__":
    main()
