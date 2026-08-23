"""Prepara um lote de fotos novas para curadoria manual no Immich.

Workflow experimental — ver docs/EXPERIMENTAL_IMMICH_WORKFLOW.md. Não toca
em photos/, organized/, nem em nenhum ficheiro usado pelo pipeline principal.

Separa a pasta de origem em três áreas dentro de
batches_staging/<batch-name>/:

  for_immich/  sobreviventes: ainda não estão em backup (índice de hashes
               partilhado), não parecem documentos, não são duplicados
               secundários dentro deste lote. Aponta uma External Library
               temporária do Immich para esta pasta para curar em álbuns.
  documents/   ficheiros que parecem documentos/cartões — ficam fora da
               timeline de curadoria, mas continuam a ser guardados.
  duplicates/  cópias secundárias de conteúdo repetido dentro do próprio
               lote (mesmo hash) — idem, fora da curadoria mas guardadas.

Ficheiros já presentes em organized/ ou organized_v2/ (via o índice de
hashes partilhado) são ignorados por completo — não precisam de ser
preparados nem curados outra vez.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
import hash_index
from build_move_plan_preview import build_duplicate_info, is_document_file
from scan_media import SUPPORTED_EXTENSIONS, build_record


def log_line(path: Path, message: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} | {message}"
    print(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_batch_files(source: Path) -> list[Path]:
    return [
        p for p in source.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def build_records(files: list[Path], log_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx, path in enumerate(files, start=1):
        try:
            records.append(build_record(path))
            log_line(log_path, f"[{idx}/{len(files)}] Lido: {path.name}")
        except Exception as exc:
            log_line(log_path, f"[{idx}/{len(files)}] ERRO ao ler {path}: {exc}")
    return records


def classify(
    record: dict[str, Any],
    already_backed_up_hashes: set[str],
    secondary_duplicate_paths: set[str],
) -> str:
    if record["hash_sha256"] in already_backed_up_hashes:
        return "already_backed_up"
    if is_document_file(record["file_name"]):
        return "document"
    if record["file_path"] in secondary_duplicate_paths:
        return "duplicate_secondary"
    return "for_immich"


BUCKET_TO_SUBDIR = {
    "document": "documents",
    "duplicate_secondary": "duplicates",
    "for_immich": "for_immich",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepara um lote de fotos novas para curadoria manual no Immich. "
        "Sem --execute corre em dry-run."
    )
    parser.add_argument("--source", required=True, help="Pasta com as fotos novas deste lote.")
    parser.add_argument("--batch-name", required=True, help="Nome do lote (usado como nome de pasta).")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        raise FileNotFoundError(f"Pasta de origem não encontrada: {source}")

    batch_root = config.BATCHES_STAGING_ROOT / args.batch_name
    log_path = config.LOGS_DIR / f"prepare_batch_{args.batch_name}.log"

    files = find_batch_files(source)
    log_line(log_path, f"START | execute={args.execute} | source={source} | ficheiros_encontrados={len(files)}")

    records = build_records(files, log_path)
    already_backed_up_hashes = hash_index.load_indexed_hashes()
    _, secondary_duplicate_paths = build_duplicate_info(records)

    counters: Counter = Counter()
    manifest: list[dict[str, Any]] = []

    for record in records:
        bucket = classify(record, already_backed_up_hashes, secondary_duplicate_paths)
        counters[bucket] += 1

        if bucket == "already_backed_up":
            continue

        source_path = Path(record["file_path"])
        destination = batch_root / BUCKET_TO_SUBDIR[bucket] / record["file_name"]

        manifest.append(
            {
                "source_path": str(source_path),
                "destination_path": str(destination),
                "hash_sha256": record["hash_sha256"],
                "bucket": bucket,
            }
        )

        if not args.execute:
            log_line(log_path, f"DRY_RUN_COPY | {bucket} | {source_path} -> {destination}")
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.stat().st_size == source_path.stat().st_size:
            log_line(log_path, f"SKIPPED_EXISTING | {bucket} | {destination}")
            continue
        shutil.copy2(source_path, destination)
        log_line(log_path, f"COPIED | {bucket} | {source_path} -> {destination}")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execute": args.execute,
        "batch_name": args.batch_name,
        "source": str(source),
        "batch_root": str(batch_root),
        "for_immich_dir": str(batch_root / "for_immich"),
        "counters": dict(counters),
        "total_files_found": len(files),
    }

    if args.execute:
        summary_path = batch_root / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        manifest_path = batch_root / "manifest.jsonl"
        with manifest_path.open("w", encoding="utf-8") as f:
            for row in manifest:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    log_line(log_path, f"END | {json.dumps(dict(counters), ensure_ascii=False)}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.execute and counters["for_immich"] > 0:
        print(
            f"\nPróximo passo: cria uma External Library no Immich (só-leitura) "
            f"a apontar para:\n  {batch_root / 'for_immich'}"
        )


if __name__ == "__main__":
    main()
