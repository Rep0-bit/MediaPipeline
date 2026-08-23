"""Exporta a curadoria feita no Immich (álbuns) para a pasta final de backup.

Workflow experimental — ver docs/EXPERIMENTAL_IMMICH_WORKFLOW.md. Não toca
em organized/ nem em nada usado pelo pipeline principal.

Lê os álbuns via API do Immich. Para cada asset de um álbum cujo
originalPath caia dentro da pasta for_immich/ deste lote (produzida por
prepare_batch.py), copia o ficheiro para
organized_v2/<nome-do-álbum-sanitizado>/. O que ficou em for_immich/ e não
está em nenhum álbum (segundo o manifest.jsonl do prepare_batch.py) vai para
organized_v2/_GERAL/<batch-name>/. As pastas documents/ e duplicates/
produzidas por prepare_batch.py nunca passam pelo Immich — são copiadas
diretamente para organized_v2/_GERAL/<batch-name>/_DOCUMENTOS/ e
_DUPLICADOS/.

Requer a variável de ambiente IMMICH_API_KEY (gerar em Definições da conta
-> API Keys, no Immich). Nunca aceite como argumento de linha de comandos
nem escrita em ficheiro.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
import hash_index
from apply_simple_sort import classify_existing, resolve_destination
from build_move_plan_preview import safe_folder_part
from scan_media import sha256_file

# Convenção fixa exigida no docker-compose.yml do Immich:
#   ./batches_staging:/mnt/batches_staging:ro
IMMICH_BATCHES_MOUNT_PREFIX = "/mnt/batches_staging"


def log_line(path: Path, message: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} | {message}"
    print(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def api_get(path: str, api_key: str) -> Any:
    req = urllib.request.Request(
        f"{config.IMMICH_API_URL}{path}",
        headers={"x-api-key": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Immich API devolveu {exc.code} em {path}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Não foi possível contactar o Immich em {config.IMMICH_API_URL}{path}: {exc}"
        ) from exc


def original_path_to_local(original_path: str) -> Path | None:
    if not original_path.startswith(IMMICH_BATCHES_MOUNT_PREFIX):
        return None
    relative = original_path[len(IMMICH_BATCHES_MOUNT_PREFIX):].lstrip("/")
    return config.BATCHES_STAGING_ROOT / Path(*relative.split("/"))


def load_manifest(batch_root: Path) -> list[dict[str, Any]]:
    manifest_path = batch_root / "manifest.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"manifest.jsonl não encontrado em {batch_root} — corre prepare_batch.py --execute primeiro."
        )
    rows = []
    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def copy_and_index(source: Path, destination: Path, execute: bool, newly_indexed: list[dict]) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    status = classify_existing(source, destination)
    if status == "exists_same_size":
        return f"skipped_existing -> {destination}"

    final_destination = resolve_destination(source, destination)
    if not execute:
        return f"dry_run_copy -> {final_destination}"

    shutil.copy2(source, final_destination)
    newly_indexed.append(
        {
            "hash_sha256": sha256_file(final_destination),
            "file_path": str(final_destination),
            "size_bytes": final_destination.stat().st_size,
        }
    )
    return f"copied -> {final_destination}"


def copy_tree(source_dir: Path, dest_dir: Path, execute: bool, newly_indexed: list[dict], log_path: Path, label: str) -> int:
    if not source_dir.exists():
        return 0
    count = 0
    for source_file in source_dir.rglob("*"):
        if not source_file.is_file():
            continue
        destination = dest_dir / source_file.name
        result = copy_and_index(source_file, destination, execute, newly_indexed)
        log_line(log_path, f"{label} | {source_file.name} | {result}")
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporta os álbuns curados no Immich para organized_v2/. Sem --execute corre em dry-run."
    )
    parser.add_argument("--batch-name", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--cleanup-staging",
        action="store_true",
        help="Depois de um export bem sucedido, remove batches_staging/<lote>/ "
        "(a cópia intermédia — o resultado já está em organized_v2/). Não apaga "
        "nada no Immich nem os ficheiros de origem do lote. Ação separada e "
        "explícita: requer --execute na mesma chamada, nunca corre sozinha nem "
        "por omissão.",
    )
    args = parser.parse_args()

    if args.cleanup_staging and not args.execute:
        raise SystemExit(
            "--cleanup-staging requer --execute (em dry-run não há nada exportado para poder limpar)."
        )

    api_key = os.environ.get("IMMICH_API_KEY")
    if not api_key:
        raise SystemExit(
            "Falta a variável de ambiente IMMICH_API_KEY "
            "(gerar em Definições da conta -> API Keys, no Immich)."
        )

    batch_root = config.BATCHES_STAGING_ROOT / args.batch_name
    for_immich_dir = batch_root / "for_immich"
    log_path = config.LOGS_DIR / f"export_from_immich_{args.batch_name}.log"

    manifest = load_manifest(batch_root)
    for_immich_entries = [row for row in manifest if row["bucket"] == "for_immich"]
    uncategorized_paths = {row["destination_path"] for row in for_immich_entries}

    log_line(
        log_path,
        f"START | execute={args.execute} | batch={args.batch_name} | "
        f"for_immich_ficheiros={len(uncategorized_paths)}",
    )

    albums = api_get("/albums", api_key)
    log_line(log_path, f"Encontrados {len(albums)} álbuns no Immich (todos, não só deste lote).")

    counters: Counter = Counter()
    newly_indexed: list[dict[str, Any]] = []

    for album in albums:
        album_detail = api_get(f"/albums/{album['id']}", api_key)
        album_name = album_detail.get("albumName", "Untitled Album")
        assets = album_detail.get("assets", [])

        relevant = []
        for asset in assets:
            local_path = original_path_to_local(asset.get("originalPath", ""))
            if local_path is not None and str(local_path) in uncategorized_paths:
                relevant.append(local_path)

        if not relevant:
            continue  # álbum não relacionado com este lote

        folder_name = safe_folder_part(album_name)
        dest_folder = config.ORGANIZED_V2_ROOT / folder_name

        for local_path in relevant:
            destination = dest_folder / local_path.name
            result = copy_and_index(local_path, destination, args.execute, newly_indexed)
            log_line(log_path, f"ALBUM[{album_name}] | {local_path.name} | {result}")
            counters[f"album:{album_name}"] += 1
            uncategorized_paths.discard(str(local_path))

    # O que sobrou em for_immich/ sem álbum -> _GERAL
    geral_dir = config.ORGANIZED_V2_ROOT / "_GERAL" / args.batch_name
    for path_str in sorted(uncategorized_paths):
        local_path = Path(path_str)
        destination = geral_dir / local_path.name
        result = copy_and_index(local_path, destination, args.execute, newly_indexed)
        log_line(log_path, f"SEM_ALBUM | {local_path.name} | {result}")
        counters["sem_album"] += 1

    # documents/ e duplicates/ nunca passam pelo Immich — cópia direta
    counters["documentos"] = copy_tree(
        batch_root / "documents", geral_dir / "_DOCUMENTOS", args.execute, newly_indexed, log_path, "DOCUMENTO"
    )
    counters["duplicados"] = copy_tree(
        batch_root / "duplicates", geral_dir / "_DUPLICADOS", args.execute, newly_indexed, log_path, "DUPLICADO"
    )

    if args.execute:
        hash_index.append_indexed_files(newly_indexed)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execute": args.execute,
        "batch_name": args.batch_name,
        "organized_v2_root": str(config.ORGANIZED_V2_ROOT),
        "counters": dict(counters),
        "staging_cleaned_up": False,
    }
    log_line(log_path, f"END | {json.dumps(dict(counters), ensure_ascii=False)}")

    # Chegar aqui sem exceção significa que todas as cópias/registos acima
    # foram bem sucedidos — condição mínima para ser seguro limpar o staging.
    if args.cleanup_staging:
        shutil.rmtree(batch_root)
        summary["staging_cleaned_up"] = True
        log_line(log_path, f"CLEANUP_STAGING | removido {batch_root}")
        print(f"Limpeza: {batch_root} removido (o resultado já está em {config.ORGANIZED_V2_ROOT}).")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
