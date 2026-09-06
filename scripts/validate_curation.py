"""Valida a curadoria feita no Immich antes do export.

Workflow experimental — ver docs/EXPERIMENTAL_IMMICH_WORKFLOW.md. Só lê a
API do Immich; não altera nada no Immich, em disco, ou no índice de
hashes. Produz um relatório para revisão manual — nada aqui é corrigido
automaticamente, cabe ao utilizador decidir o que fazer com cada aviso
antes de correr export_from_immich.py --execute.

Verificações:
  - Duplicados entre álbuns: o mesmo asset (mesmo ID) presente em mais do
    que um álbum deste lote — seria copiado para as duas pastas de
    destino no export.
  - Duplicados percetuais: assets deste lote que o próprio Immich já
    identificou como semelhantes entre si (campo duplicateId da deteção
    de duplicados do Immich), sobretudo se acabaram em álbuns diferentes.
  - Outliers de localização por álbum: assets cuja localização está
    muito mais longe do que o habitual da localização típica do resto do
    álbum (mediana + desvio absoluto mediano, adaptado a cada álbum).
  - Outliers de data por álbum: o mesmo raciocínio, mas por data.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from export_from_immich import IMMICH_BATCHES_MOUNT_PREFIX, api_get, original_path_to_local
from propose_multiday_links_gps import haversine_m

MIN_SAMPLES_FOR_OUTLIER_CHECK = 3


def collect_batch_assets(batch_name: str, api_key: str) -> list[dict[str, Any]]:
    """Devolve um registo por asset deste lote que está em pelo menos um álbum,
    com {asset_id, file_name, album_name, latitude, longitude, date, duplicate_id}."""
    batch_prefix = f"{IMMICH_BATCHES_MOUNT_PREFIX}/{batch_name}/for_immich"
    albums = api_get("/albums", api_key)

    records: list[dict[str, Any]] = []
    for album in albums:
        detail = api_get(f"/albums/{album['id']}", api_key)
        album_name = detail.get("albumName", "Untitled Album")

        for asset in detail.get("assets", []):
            original_path = asset.get("originalPath", "")
            if not original_path.startswith(batch_prefix):
                continue

            exif = asset.get("exifInfo") or {}
            date_str = exif.get("dateTimeOriginal")
            date_value = None
            if date_str:
                try:
                    date_value = datetime.fromisoformat(date_str)
                except ValueError:
                    date_value = None

            records.append(
                {
                    "asset_id": asset["id"],
                    "file_name": asset.get("originalFileName", Path(original_path).name),
                    "album_name": album_name,
                    "latitude": exif.get("latitude"),
                    "longitude": exif.get("longitude"),
                    "date": date_value,
                    "duplicate_id": asset.get("duplicateId"),
                }
            )

    return records


def check_cross_album_duplicates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_asset[row["asset_id"]].append(row)

    findings = []
    for asset_id, rows in by_asset.items():
        album_names = sorted({r["album_name"] for r in rows})
        if len(album_names) > 1:
            findings.append(
                {
                    "file_name": rows[0]["file_name"],
                    "asset_id": asset_id,
                    "albums": album_names,
                }
            )
    return findings


def check_perceptual_duplicates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Um asset em 2 álbuns produz 2 linhas em `records` — deduplicar por
    # asset_id primeiro, para só assinalar quando o Immich agrupou
    # assets DIFERENTES (não a mesma foto contada duas vezes por estar
    # em vários álbuns, isso já é assinalado por check_cross_album_duplicates).
    by_asset: dict[str, dict[str, Any]] = {}
    asset_albums: dict[str, set[str]] = defaultdict(set)
    for row in records:
        by_asset[row["asset_id"]] = row
        asset_albums[row["asset_id"]].add(row["album_name"])

    by_dup_id: dict[str, list[str]] = defaultdict(list)
    for asset_id, row in by_asset.items():
        if row["duplicate_id"]:
            by_dup_id[row["duplicate_id"]].append(asset_id)

    findings = []
    for dup_id, asset_ids in by_dup_id.items():
        if len(asset_ids) < 2:
            continue
        album_names = sorted({album for aid in asset_ids for album in asset_albums[aid]})
        findings.append(
            {
                "duplicate_id": dup_id,
                "files": [by_asset[aid]["file_name"] for aid in asset_ids],
                "albums": album_names,
                "cross_album": len(album_names) > 1,
            }
        )
    return findings


def check_location_outliers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_album: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if row["latitude"] is not None and row["longitude"] is not None:
            by_album[row["album_name"]].append(row)

    findings = []
    for album_name, rows in by_album.items():
        if len(rows) < MIN_SAMPLES_FOR_OUTLIER_CHECK:
            continue

        med_lat = statistics.median(r["latitude"] for r in rows)
        med_lon = statistics.median(r["longitude"] for r in rows)
        distances_km = [
            haversine_m(r["latitude"], r["longitude"], med_lat, med_lon) / 1000.0 for r in rows
        ]
        typical_spread_km = statistics.median(distances_km)
        threshold_km = max(2.0, 3.0 * typical_spread_km)

        for row, distance_km in zip(rows, distances_km):
            if distance_km > threshold_km:
                findings.append(
                    {
                        "file_name": row["file_name"],
                        "album_name": album_name,
                        "distance_km_from_typical": round(distance_km, 1),
                        "threshold_km": round(threshold_km, 1),
                    }
                )
    return findings


def check_date_outliers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_album: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if row["date"] is not None:
            by_album[row["album_name"]].append(row)

    findings = []
    for album_name, rows in by_album.items():
        if len(rows) < MIN_SAMPLES_FOR_OUTLIER_CHECK:
            continue

        epochs = [r["date"].timestamp() for r in rows]
        med_epoch = statistics.median(epochs)
        deviations_days = [abs(e - med_epoch) / 86400.0 for e in epochs]
        typical_spread_days = statistics.median(deviations_days)
        # Limiar generoso de propósito: álbuns de vários dias (ex.: férias de
        # 12 dias) concentram-se muitas vezes em 1-2 dias de pico, o que faz
        # o desvio absoluto mediano subestimar o espalhamento "normal". Um
        # multiplicador e piso maiores evitam assinalar isso como outlier,
        # mantendo a deteção para desvios claramente fora de série (semanas/
        # meses de distância).
        threshold_days = max(5.0, 3.0 * typical_spread_days)

        for row, deviation_days in zip(rows, deviations_days):
            if deviation_days > threshold_days:
                findings.append(
                    {
                        "file_name": row["file_name"],
                        "album_name": album_name,
                        "date": row["date"].isoformat(),
                        "days_from_typical": round(deviation_days, 1),
                        "threshold_days": round(threshold_days, 1),
                    }
                )
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Valida a curadoria no Immich antes do export (só lê, nunca altera nada)."
    )
    parser.add_argument("--batch-name", required=True)
    args = parser.parse_args()

    api_key = os.environ.get("IMMICH_API_KEY")
    if not api_key:
        raise SystemExit(
            "Falta a variável de ambiente IMMICH_API_KEY "
            "(gerar em Definições da conta -> API Keys, no Immich)."
        )

    print(f"A ler álbuns do Immich para o lote '{args.batch_name}'...")
    records = collect_batch_assets(args.batch_name, api_key)
    print(f"{len(records)} entradas (asset, álbum) encontradas para este lote.\n")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "batch_name": args.batch_name,
        "total_asset_album_entries": len(records),
        "cross_album_duplicates": check_cross_album_duplicates(records),
        "perceptual_duplicates": check_perceptual_duplicates(records),
        "location_outliers": check_location_outliers(records),
        "date_outliers": check_date_outliers(records),
    }

    def show(title: str, findings: list[dict[str, Any]]) -> None:
        print(f"=== {title}: {len(findings)} ===")
        for f in findings[:20]:
            print(f"  {json.dumps(f, ensure_ascii=False)}")
        if len(findings) > 20:
            print(f"  ... e mais {len(findings) - 20}")
        print()

    show("Duplicados entre álbuns", report["cross_album_duplicates"])
    show("Duplicados percetuais (Immich)", report["perceptual_duplicates"])
    show("Outliers de localização", report["location_outliers"])
    show("Outliers de data", report["date_outliers"])

    report_path = config.BATCHES_STAGING_ROOT / args.batch_name / "validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"Relatório completo escrito em: {report_path}")


if __name__ == "__main__":
    main()
