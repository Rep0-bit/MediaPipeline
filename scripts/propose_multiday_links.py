from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_SEMANTICS_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\semantics\cluster_semantics.json")
DEFAULT_OUTPUT_PAIRS_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\links\multiday_candidate_pairs.json")
DEFAULT_OUTPUT_GROUPS_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\links\multiday_candidate_groups.json")
DEFAULT_OUTPUT_REVIEW_CSV = Path(r"C:\Tools\MediaPipeline\pipeline_state\links\multiday_review.csv")
DEFAULT_OUTPUT_SUMMARY_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\links\multiday_summary.json")

STOPWORDS = {
    "de", "da", "do", "das", "dos", "a", "o", "e", "em", "no", "na", "nos", "nas",
    "um", "uma", "por", "para", "com", "sem", "ao", "aos", "as", "os",
    "the", "and", "for", "with", "from", "this", "that"
}

GENERIC_EVENT_NAMES = {
    "evento",
    "eventos",
    "imagem",
    "imagens",
    "evento de imagens",
    "captura de imagens",
    "captura de imagem",
    "fotografias de evento",
    "fotografias",
    "fotos",
    "sessao de fotos",
    "capturas diarias",
    "captura",
    "notas",
    "nota",
    "relatorio",
    "relatorio diario",
    "codigo qr",
    "qrcode",
    "reuniao",
    "reuniao diaria",
    "reuniao de equipa",
    "reuniao de staff",
    "evento digital",
    "evento semanal",
    "evento outdoor",
    "evento desportivo",
    "recolha de dados",
    "evento de recolha de dados",
    "monitoramento de evento",
    "monitoramento de seguranca",
    "ambiente interior",
    "ambiente exterior",
    "atividade diaria",
    "atividade de lazer",
    "atividade ao ar livre",
    "viagem",
    "compras",
    "compras online",
    "teste de camera",
    "imagem de teste",
    "evento-0026",
    "evento de teste",
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.lower().strip()


def tokenise(value: str) -> set[str]:
    value = normalize_text(value)
    parts = re.findall(r"[a-z0-9]+", value)
    return {p for p in parts if len(p) >= 3 and p not in STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_semantics(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_day(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


def is_generic_event_name(value: str) -> bool:
    norm = normalize_text(value)
    if not norm:
        return True
    if norm in GENERIC_EVENT_NAMES:
        return True

    # padrões muito genéricos
    generic_patterns = [
        r"^evento(?:-\d+)?$",
        r"^imagem(?: de teste)?$",
        r"^captura(?: de imagens?)?$",
        r"^fotografias?(?: de evento)?$",
        r"^reuniao(?: diaria)?$",
        r"^notas?$",
    ]
    for pattern in generic_patterns:
        if re.fullmatch(pattern, norm):
            return True

    return False


def pick_best_group_name(member_rows: list[dict[str, Any]]) -> str:
    non_generic = [
        row.get("event_name_suggestion", "").strip()
        for row in member_rows
        if row.get("event_name_suggestion", "").strip()
        and not is_generic_event_name(row.get("event_name_suggestion", ""))
    ]
    generic = [
        row.get("event_name_suggestion", "").strip()
        for row in member_rows
        if row.get("event_name_suggestion", "").strip()
    ]

    if non_generic:
        return Counter(non_generic).most_common(1)[0][0]
    if generic:
        return Counter(generic).most_common(1)[0][0]
    return "Evento multi-dia"


def score_pair(a: dict[str, Any], b: dict[str, Any], max_gap_days: int) -> dict[str, Any] | None:
    day_a = parse_day(a["event_day"])
    day_b = parse_day(b["event_day"])
    if day_a is None or day_b is None:
        return None

    gap_days = (day_b - day_a).days
    if gap_days < 1 or gap_days > max_gap_days:
        return None

    score = 0.0
    reasons: list[str] = []

    if gap_days == 1:
        score += 0.20
        reasons.append("dias consecutivos")
    elif gap_days == 2:
        score += 0.10
        reasons.append("dias próximos")

    name_a = a.get("event_name_suggestion", "")
    name_b = b.get("event_name_suggestion", "")
    generic_a = is_generic_event_name(name_a)
    generic_b = is_generic_event_name(name_b)

    name_sim = jaccard(tokenise(name_a), tokenise(name_b))

    # peso reduzido quando os nomes são genéricos
    if not generic_a and not generic_b:
        if name_sim >= 0.60:
            score += 0.25
            reasons.append("nome sugerido muito semelhante")
        elif name_sim >= 0.30:
            score += 0.15
            reasons.append("nome sugerido parcialmente semelhante")
        elif name_sim > 0:
            score += 0.05
            reasons.append("nome sugerido com alguma sobreposição")
    elif generic_a and generic_b:
        if name_sim >= 0.60:
            score += 0.05
            reasons.append("nome genérico semelhante (peso reduzido)")
        elif name_sim > 0:
            score += 0.02
            reasons.append("nome genérico com ligeira sobreposição")
    else:
        if name_sim >= 0.60:
            score += 0.08
            reasons.append("um nome específico e outro genérico com semelhança")
        elif name_sim >= 0.30:
            score += 0.04
            reasons.append("um nome específico e outro genérico com alguma semelhança")

    tags_a = {normalize_text(x) for x in a.get("tags", []) if str(x).strip()}
    tags_b = {normalize_text(x) for x in b.get("tags", []) if str(x).strip()}
    tag_overlap = len(tags_a & tags_b)
    if tag_overlap >= 3:
        score += 0.25
        reasons.append("muitas tags em comum")
    elif tag_overlap >= 1:
        score += 0.10
        reasons.append("algumas tags em comum")

    loc_a = normalize_text(a.get("location_hint", ""))
    loc_b = normalize_text(b.get("location_hint", ""))
    if loc_a and loc_b and loc_a == loc_b:
        score += 0.20
        reasons.append("mesma pista de localização")

    desc_sim = jaccard(tokenise(a.get("short_description", "")), tokenise(b.get("short_description", "")))
    if desc_sim >= 0.50:
        score += 0.15
        reasons.append("descrição visual semelhante")
    elif desc_sim >= 0.25:
        score += 0.08
        reasons.append("descrição visual parcialmente semelhante")

    keywords_a = {normalize_text(x) for x in a.get("likely_same_event_keywords", []) if str(x).strip()}
    keywords_b = {normalize_text(x) for x in b.get("likely_same_event_keywords", []) if str(x).strip()}
    kw_overlap = len(keywords_a & keywords_b)
    if kw_overlap >= 2:
        score += 0.10
        reasons.append("keywords multi-dia semelhantes")

    conf_bonus_map = {"low": 0.00, "medium": 0.03, "high": 0.05}
    conf_bonus = min(
        conf_bonus_map.get(a.get("semantic_confidence", "low"), 0.0),
        conf_bonus_map.get(b.get("semantic_confidence", "low"), 0.0),
    )
    if conf_bonus > 0:
        score += conf_bonus
        reasons.append("boa confiança semântica")

    # pequena penalização se ambos os nomes forem genéricos
    if generic_a and generic_b:
        score -= 0.05
        reasons.append("penalização por nomes demasiado genéricos")

    confidence = None
    if score >= 0.70:
        confidence = "high"
    elif score >= 0.50:
        confidence = "medium"

    if confidence is None:
        return None

    if not generic_a and not generic_b:
        suggested_event_name = name_a if len(name_a) >= len(name_b) else name_b
    elif not generic_a:
        suggested_event_name = name_a
    elif not generic_b:
        suggested_event_name = name_b
    else:
        suggested_event_name = name_a or name_b or "Evento multi-dia"

    return {
        "cluster_id_a": a["cluster_id"],
        "event_day_a": a["event_day"],
        "cluster_id_b": b["cluster_id"],
        "event_day_b": b["event_day"],
        "gap_days": gap_days,
        "score": round(score, 3),
        "confidence": confidence,
        "suggested_event_name": suggested_event_name,
        "generic_name_a": generic_a,
        "generic_name_b": generic_b,
        "reasons": reasons,
    }


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: str, b: str) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def main() -> None:
    parser = argparse.ArgumentParser(description="Propõe ligações multi-dia entre clusters sem alterar pastas.")
    parser.add_argument("--semantics", default=str(DEFAULT_SEMANTICS_JSON))
    parser.add_argument("--output-pairs", default=str(DEFAULT_OUTPUT_PAIRS_JSON))
    parser.add_argument("--output-groups", default=str(DEFAULT_OUTPUT_GROUPS_JSON))
    parser.add_argument("--output-review-csv", default=str(DEFAULT_OUTPUT_REVIEW_CSV))
    parser.add_argument("--summary", default=str(DEFAULT_OUTPUT_SUMMARY_JSON))
    parser.add_argument("--max-gap-days", type=int, default=2)
    args = parser.parse_args()

    semantics = load_semantics(Path(args.semantics))
    semantics = [row for row in semantics if "cluster_id" in row and "error" not in row]
    semantics.sort(key=lambda r: (r["event_day"], r["cluster_id"]))

    candidate_pairs: list[dict[str, Any]] = []

    for i, a in enumerate(semantics):
        for b in semantics[i + 1:]:
            pair = score_pair(a, b, args.max_gap_days)
            if pair is None:
                continue
            candidate_pairs.append(pair)

    candidate_pairs.sort(key=lambda p: (-p["score"], p["event_day_a"], p["cluster_id_a"], p["cluster_id_b"]))

    uf = UnionFind()
    for pair in candidate_pairs:
        if pair["confidence"] == "high":
            uf.union(pair["cluster_id_a"], pair["cluster_id_b"])

    grouped: dict[str, set[str]] = defaultdict(set)
    for pair in candidate_pairs:
        if pair["confidence"] == "high":
            grouped[uf.find(pair["cluster_id_a"])].add(pair["cluster_id_a"])
            grouped[uf.find(pair["cluster_id_b"])].add(pair["cluster_id_b"])

    semantics_by_cluster = {row["cluster_id"]: row for row in semantics}

    candidate_groups: list[dict[str, Any]] = []
    group_counter = 1
    for _, members in grouped.items():
        if len(members) <= 1:
            continue

        member_rows = [semantics_by_cluster[m] for m in sorted(members)]
        event_days = sorted({r["event_day"] for r in member_rows})
        group_id = f"multiday-{group_counter:04d}"
        group_counter += 1

        candidate_groups.append(
            {
                "group_id": group_id,
                "confidence": "high",
                "cluster_ids": [r["cluster_id"] for r in member_rows],
                "event_days": event_days,
                "suggested_event_name": pick_best_group_name(member_rows),
                "member_count": len(member_rows),
            }
        )

    review_rows: list[dict[str, Any]] = []

    for group in candidate_groups:
        review_rows.append(
            {
                "decision": "",
                "proposal_type": "group",
                "proposal_id": group["group_id"],
                "confidence": group["confidence"],
                "cluster_ids": ";".join(group["cluster_ids"]),
                "event_days": ";".join(group["event_days"]),
                "suggested_event_name": group["suggested_event_name"],
                "notes": "Mesmo evento multi-dia sugerido",
            }
        )

    for pair in candidate_pairs:
        if pair["confidence"] == "medium":
            review_rows.append(
                {
                    "decision": "",
                    "proposal_type": "pair",
                    "proposal_id": f"{pair['cluster_id_a']}__{pair['cluster_id_b']}",
                    "confidence": pair["confidence"],
                    "cluster_ids": f"{pair['cluster_id_a']};{pair['cluster_id_b']}",
                    "event_days": f"{pair['event_day_a']};{pair['event_day_b']}",
                    "suggested_event_name": pair["suggested_event_name"],
                    "notes": " | ".join(pair["reasons"]),
                }
            )

    output_pairs = Path(args.output_pairs)
    output_groups = Path(args.output_groups)
    output_csv = Path(args.output_review_csv)
    output_summary = Path(args.summary)

    output_pairs.parent.mkdir(parents=True, exist_ok=True)

    with output_pairs.open("w", encoding="utf-8") as f:
        json.dump(candidate_pairs, f, ensure_ascii=False, indent=2)

    with output_groups.open("w", encoding="utf-8") as f:
        json.dump(candidate_groups, f, ensure_ascii=False, indent=2)

    with output_csv.open("w", encoding="utf-8", newline="") as f:
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

    summary = {
        "generated_at_utc": datetime.now().isoformat(),
        "input_cluster_semantics": len(semantics),
        "candidate_pair_count": len(candidate_pairs),
        "high_pair_count": sum(1 for x in candidate_pairs if x["confidence"] == "high"),
        "medium_pair_count": sum(1 for x in candidate_pairs if x["confidence"] == "medium"),
        "candidate_group_count": len(candidate_groups),
        "review_csv_rows": len(review_rows),
        "max_gap_days": args.max_gap_days,
    }

    with output_summary.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Pairs JSON:   {output_pairs}")
    print(f"Groups JSON:  {output_groups}")
    print(f"Review CSV:   {output_csv}")
    print(f"Summary JSON: {output_summary}")


if __name__ == "__main__":
    main()