from __future__ import annotations

import argparse
import base64
import json
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CLUSTERS_PATH = Path(r"C:\Tools\MediaPipeline\pipeline_state\registry\event_cluster_preview.json")
DEFAULT_OUTPUT_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\semantics\cluster_semantics.json")
DEFAULT_OUTPUT_JSONL = Path(r"C:\Tools\MediaPipeline\pipeline_state\semantics\cluster_semantics.jsonl")
DEFAULT_SUMMARY_JSON = Path(r"C:\Tools\MediaPipeline\pipeline_state\semantics\cluster_semantics_summary.json")

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

GENERIC_EVENT_NAMES = {
    "evento",
    "eventos",
    "imagem",
    "imagens",
    "captura",
    "captura de imagem",
    "captura de imagens",
    "captura de evento",
    "evento de imagens",
    "fotografias",
    "fotos",
    "fotografias de evento",
    "nota",
    "notas",
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
    "viagem",
    "compras",
    "compras online",
    "teste de camera",
    "imagem de teste",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "event_name_suggestion": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "short_description": {"type": "string"},
        "location_hint": {"type": "string"},
        "likely_same_event_keywords": {"type": "array", "items": {"type": "string"}},
        "semantic_confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"]
        }
    },
    "required": [
        "event_name_suggestion",
        "tags",
        "short_description",
        "location_hint",
        "likely_same_event_keywords",
        "semantic_confidence"
    ]
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.lower().strip()


def sanitize_label(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:60] if value else "evento"


def is_generic_event_name(value: str) -> bool:
    norm = normalize_text(value)
    if not norm:
        return True
    if norm in GENERIC_EVENT_NAMES:
        return True

    generic_patterns = [
        r"^evento(?:-\d+)?$",
        r"^imagem(?: de teste)?$",
        r"^captura(?: de imagens?)?$",
        r"^captura de evento$",
        r"^fotografias?(?: de evento)?$",
        r"^reuniao(?: diaria)?$",
        r"^notas?$",
    ]
    for pattern in generic_patterns:
        if re.fullmatch(pattern, norm):
            return True

    return False


def title_pt(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    return value[0].upper() + value[1:]


def choose_specific_terms(tags: list[str]) -> list[str]:
    weak_terms = {
        "evento", "eventos", "imagem", "imagens", "foto", "fotos",
        "captura", "notas", "reuniao", "reunião", "formal",
        "digital", "diario", "diário"
    }
    chosen: list[str] = []
    for tag in tags:
        clean = tag.strip()
        norm = normalize_text(clean)
        if not clean:
            continue
        if norm in weak_terms:
            continue
        if len(norm) < 3:
            continue
        chosen.append(clean)
        if len(chosen) >= 2:
            break
    return chosen


def improve_event_name(
    event_name: str,
    tags: list[str],
    description: str,
    location_hint: str,
) -> str:
    if not is_generic_event_name(event_name):
        return event_name.strip()

    specific_tags = choose_specific_terms(tags)

    loc = location_hint.strip()
    desc = description.strip()

    if specific_tags and loc:
        return title_pt(f"{specific_tags[0]} em {loc}")

    if len(specific_tags) >= 2:
        return title_pt(f"{specific_tags[0]} e {specific_tags[1]}")

    if specific_tags:
        return title_pt(specific_tags[0])

    if loc:
        generic_loc_map = {
            "interior": "Atividade em interior",
            "exterior": "Atividade em exterior",
        }
        loc_norm = normalize_text(loc)
        if loc_norm in generic_loc_map:
            return generic_loc_map[loc_norm]
        return title_pt(f"Atividade em {loc}")

    if desc:
        first_sentence = re.split(r"[.!?]", desc)[0].strip()
        if first_sentence:
            return title_pt(first_sentence[:80])

    return "Evento não específico"


def load_clusters(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_image_file(path_str: str) -> bool:
    return Path(path_str).suffix.lower() in IMAGE_SUFFIXES


def encode_image_base64(path_str: str) -> str:
    data = Path(path_str).read_bytes()
    return base64.b64encode(data).decode("utf-8")


def base_url_from_endpoint(endpoint: str) -> str:
    return endpoint.rsplit("/api/", 1)[0]


def health_check(base_url: str) -> dict[str, Any]:
    url = f"{base_url}/api/ps"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post_chat(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} | {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"URL error | {exc}") from exc


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_response_content(response_json: dict[str, Any]) -> dict[str, Any]:
    content = response_json["message"]["content"]
    if isinstance(content, dict):
        return content

    content = strip_code_fences(str(content))

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "event_name_suggestion": "Evento",
            "tags": [],
            "short_description": content,
            "location_hint": "",
            "likely_same_event_keywords": [],
            "semantic_confidence": "low",
        }


def build_prompt(cluster: dict[str, Any], sampled_paths: list[str], vision: bool, english_mode: bool) -> str:
    file_names = [Path(item["file_name"]).name for item in cluster["files"][:8]]
    file_names_text = "\n".join(f"- {name}" for name in file_names)

    sampled_text = "\n".join(f"- {Path(p).name}" for p in sampled_paths) if sampled_paths else "- no sampled images"

    forbidden_names = (
        "Evento, Eventos, Imagem, Imagens, Captura, Captura de Imagens, "
        "Fotografias, Fotos, Notas, Relatório, Código QR, Reunião, "
        "Reunião Diária, Evento Digital"
    )

    if english_mode:
        return f"""
You are a local media-organising assistant.
Analyse ONE daily cluster only. Do not merge different days. Do not guess private identities.

Return JSON only.
All output strings must be in Portuguese (Portugal).

Critical naming rules:
- event_name_suggestion must be specific and concrete
- use 2 to 6 words
- prefer scene + activity + place type when possible
- avoid generic names completely

Forbidden generic names:
{forbidden_names}

Good examples:
- Reunião em sala
- Visita a showroom
- Exposição de mobiliário
- Atividade na piscina
- Trabalhos de construção exterior

Bad examples:
- Evento
- Reunião
- Imagem
- Captura de Evento
- Notas

If the image is ambiguous, still choose the most specific safe label possible.
If certainty is limited, lower semantic_confidence instead of using a generic title.

Cluster data:
- cluster_id: {cluster["cluster_id"]}
- event_day: {cluster["event_day"]}
- file_count: {cluster["file_count"]}
- timestamp_start: {cluster["timestamp_start"]}
- timestamp_end: {cluster["timestamp_end"]}

Sample file names:
{file_names_text}

Sampled images:
{sampled_text}

Required fields:
- event_name_suggestion
- tags
- short_description
- location_hint
- likely_same_event_keywords
- semantic_confidence
""".strip()

    return f"""
És um assistente local de organização de media.
Analisa apenas UM cluster diário. Não juntes dias diferentes. Não uses nomes privados.

Responde apenas em JSON.
Usa Português de Portugal.

Regras críticas para o nome do evento:
- `event_name_suggestion` deve ser específico e concreto
- usar entre 2 e 6 palavras
- preferir contexto visual + atividade + tipo de local, quando possível
- evitar completamente nomes genéricos

Nomes genéricos proibidos:
{forbidden_names}

Exemplos bons:
- Reunião em sala
- Visita a showroom
- Exposição de mobiliário
- Atividade na piscina
- Trabalhos de construção exterior

Exemplos maus:
- Evento
- Reunião
- Imagem
- Captura de Evento
- Notas

Se a imagem for ambígua, escolhe mesmo assim o nome mais específico e seguro possível.
Se houver pouca certeza, reduz `semantic_confidence` em vez de usar um nome genérico.

Dados do cluster:
- cluster_id: {cluster["cluster_id"]}
- event_day: {cluster["event_day"]}
- file_count: {cluster["file_count"]}
- timestamp_start: {cluster["timestamp_start"]}
- timestamp_end: {cluster["timestamp_end"]}

Amostra de ficheiros:
{file_names_text}

Imagens amostradas:
{sampled_text}

Campos obrigatórios:
- event_name_suggestion
- tags
- short_description
- location_hint
- likely_same_event_keywords
- semantic_confidence
""".strip()


def build_payload(
    model: str,
    prompt: str,
    image_paths: list[str],
    use_format: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    if image_paths:
        payload["messages"][0]["images"] = [encode_image_base64(p) for p in image_paths]

    if use_format:
        payload["format"] = SCHEMA

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera semântica por cluster usando Ollama.")
    parser.add_argument("--clusters", default=str(DEFAULT_CLUSTERS_PATH))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-jsonl", default=str(DEFAULT_OUTPUT_JSONL))
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--endpoint", default="http://localhost:11434/api/chat")
    parser.add_argument("--model", default="gemma3:latest")
    parser.add_argument("--vision", action="store_true", help="Ativa análise com imagens.")
    parser.add_argument("--max-images", type=int, default=1)
    parser.add_argument("--use-format", action="store_true", help="Ativa structured output.")
    parser.add_argument("--fallback-text-only", action="store_true", help="Se falhar com visão, repete sem imagens.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--cluster-ids", default="")
    parser.add_argument("--min-file-count", type=int, default=1)
    args = parser.parse_args()

    base_url = base_url_from_endpoint(args.endpoint)
    try:
        health = health_check(base_url)
    except Exception as exc:
        raise SystemExit(f"Ollama health check failed: {exc}")

    clusters = load_clusters(Path(args.clusters))

    wanted_cluster_ids = {x.strip() for x in args.cluster_ids.split(",") if x.strip()}
    if wanted_cluster_ids:
        clusters = [c for c in clusters if c["cluster_id"] in wanted_cluster_ids]

    clusters = [c for c in clusters if int(c.get("file_count", 0)) >= args.min_file_count]

    if args.limit > 0:
        clusters = clusters[:args.limit]

    results: list[dict[str, Any]] = []
    counters: dict[str, int] = {}

    def bump(key: str) -> None:
        counters[key] = counters.get(key, 0) + 1

    english_mode = "llama3.2-vision" in args.model.lower()

    for cluster in clusters:
        image_paths = []
        if args.vision:
            image_paths = [
                item["file_path"]
                for item in cluster["files"]
                if is_image_file(item["file_path"])
            ][: args.max_images]

        prompt = build_prompt(
            cluster=cluster,
            sampled_paths=image_paths,
            vision=bool(image_paths),
            english_mode=english_mode,
        )

        payload = build_payload(
            model=args.model,
            prompt=prompt,
            image_paths=image_paths,
            use_format=args.use_format,
        )

        prompt_basis = "vision" if image_paths else "text_only"

        try:
            response_json = post_chat(args.endpoint, payload)
            parsed = parse_response_content(response_json)
            used_fallback = False

        except Exception as exc:
            if image_paths and args.fallback_text_only:
                try:
                    fallback_prompt = build_prompt(
                        cluster=cluster,
                        sampled_paths=[],
                        vision=False,
                        english_mode=english_mode,
                    )
                    fallback_payload = build_payload(
                        model=args.model,
                        prompt=fallback_prompt,
                        image_paths=[],
                        use_format=args.use_format,
                    )
                    response_json = post_chat(args.endpoint, fallback_payload)
                    parsed = parse_response_content(response_json)
                    used_fallback = True
                    prompt_basis = "text_only_fallback"
                    bump("fallback_success")
                except Exception as fallback_exc:
                    used_fallback = False
                    error_row = {
                        "generated_at_utc": now_utc(),
                        "cluster_id": cluster["cluster_id"],
                        "event_day": cluster["event_day"],
                        "file_count": cluster["file_count"],
                        "model": args.model,
                        "error": f"primary={exc} | fallback={fallback_exc}",
                    }
                    results.append(error_row)
                    bump("errors")
                    print(f"[ERROR] {cluster['cluster_id']} -> {fallback_exc}")
                    continue
            else:
                error_row = {
                    "generated_at_utc": now_utc(),
                    "cluster_id": cluster["cluster_id"],
                    "event_day": cluster["event_day"],
                    "file_count": cluster["file_count"],
                    "model": args.model,
                    "error": str(exc),
                }
                results.append(error_row)
                bump("errors")
                print(f"[ERROR] {cluster['cluster_id']} -> {exc}")
                continue

        raw_event_name = str(parsed.get("event_name_suggestion", "")).strip() or "Evento"
        tags = [str(x).strip() for x in parsed.get("tags", []) if str(x).strip()]
        description = str(parsed.get("short_description", "")).strip()
        location_hint = str(parsed.get("location_hint", "")).strip()
        keywords = [str(x).strip() for x in parsed.get("likely_same_event_keywords", []) if str(x).strip()]
        semantic_confidence = str(parsed.get("semantic_confidence", "low")).strip().lower()
        if semantic_confidence not in {"low", "medium", "high"}:
            semantic_confidence = "low"

        event_name = improve_event_name(
            event_name=raw_event_name,
            tags=tags,
            description=description,
            location_hint=location_hint,
        )

        row = {
            "generated_at_utc": now_utc(),
            "cluster_id": cluster["cluster_id"],
            "event_day": cluster["event_day"],
            "file_count": cluster["file_count"],
            "timestamp_start": cluster["timestamp_start"],
            "timestamp_end": cluster["timestamp_end"],
            "model": args.model,
            "prompt_basis": prompt_basis,
            "sampled_image_count": len(image_paths),
            "used_fallback": used_fallback,
            "raw_event_name_suggestion": raw_event_name,
            "event_name_was_generic": is_generic_event_name(raw_event_name),
            "event_name_suggestion": event_name,
            "event_label_fs": sanitize_label(event_name),
            "tags": tags[:10],
            "short_description": description,
            "location_hint": location_hint,
            "likely_same_event_keywords": keywords[:10],
            "semantic_confidence": semantic_confidence,
        }

        results.append(row)
        bump("processed")
        bump(f"basis_{prompt_basis}")
        bump(f"confidence_{semantic_confidence}")

        print(f"[OK] {cluster['cluster_id']} -> {row['event_name_suggestion']}")

    output_json = Path(args.output_json)
    output_jsonl = Path(args.output_jsonl)
    summary_json = Path(args.summary)

    output_json.parent.mkdir(parents=True, exist_ok=True)

    with output_json.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with output_jsonl.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "generated_at_utc": now_utc(),
        "model": args.model,
        "health_models_visible": len(health.get("models", [])),
        "cluster_count_input": len(clusters),
        "result_counters": counters,
        "vision_enabled": args.vision,
        "max_images": args.max_images,
        "use_format": args.use_format,
        "fallback_text_only": args.fallback_text_only,
        "output_json": str(output_json),
        "output_jsonl": str(output_jsonl),
    }

    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()