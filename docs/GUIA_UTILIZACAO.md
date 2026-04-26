# Guia de Utilização

Este guia descreve o fluxo recomendado de utilização do MediaPipeline.

---

## 1. Preparação do ambiente

Ativar o ambiente virtual:

```powershell
.\.venv\Scripts\Activate.ps1
```

Confirmar a versão de Python:

```powershell
python --version
```

---

## 2. Organização base dos ficheiros

### 2.1 Scan do media
```powershell
python .\scripts\scan_media.py
```

Resultado esperado:
- criação/atualização do registo de media
- escrita em `pipeline_state\registry\media_registry.jsonl`

### 2.2 Resumo do registo
```powershell
python .\scripts\summarize_registry.py
```

Resultado esperado:
- resumo por extensões
- qualidade de metadata
- contagens por datas

### 2.3 Clusterização temporal
```powershell
python .\scripts\cluster_temporal_preview.py
```

Resultado esperado:
- enriquecimento do registo com `effective_timestamp`
- criação de preview de clusters

### 2.4 Plano de organização
```powershell
python .\scripts\build_move_plan_preview.py
```

Resultado esperado:
- proposta de organização por pastas
- ficheiros de preview e resumo

### 2.5 Aplicação da organização simples
```powershell
python .\scripts\apply_simple_sort.py --execute
```

Resultado esperado:
- criação de pastas diárias automáticas
- envio de casos ambíguos para `_REVIEW`
- envio de casos não classificados para `_GENERAL`

### 2.6 Tratamento das pastas `_REVIEW`
Depois de rever visualmente os conteúdos, o utilizador renomeia as pastas em `_REVIEW` com sufixos como:

- `_A` para aprovadas
- `_G` para general

Depois executa:

```powershell
python .\scripts\process_review_folders.py --execute
```

---

## 3. Enriquecimento semântico com Ollama

> Esta camada é opcional e experimental.  
> Os resultados devem ser interpretados como apoio à revisão manual, sobretudo na parte de sugestões multi-dia.

### 3.1 Gerar semântica por cluster
```powershell
python .\scripts\generate_cluster_semantics.py --model gemma3:latest --vision --max-images 1 --use-format --fallback-text-only --limit 100
```

O script sugere:

- `event_name_suggestion`
- `tags`
- `short_description`
- `location_hint`
- `likely_same_event_keywords`
- `semantic_confidence`

Os outputs são escritos em:

```text
pipeline_state\semantics\cluster_semantics.json
pipeline_state\semantics\cluster_semantics.jsonl
pipeline_state\semantics\cluster_semantics_summary.json
```

---

## 4. Propostas de ligações multi-dia

### 4.1 Gerar candidatos
```powershell
python .\scripts\propose_multiday_links.py --max-gap-days 2
```

Este script gera pares candidatos a pertencer ao mesmo evento.

Outputs:

```text
pipeline_state\links\multiday_candidate_pairs.json
pipeline_state\links\multiday_candidate_groups.json
pipeline_state\links\multiday_review.csv
pipeline_state\links\multiday_summary.json
```

---

## 5. Aplicação de IDs `__REV-xxxx`

> A aplicação de `__REV-xxxx` não valida que as pastas pertençam ao mesmo evento.  
> Apenas sinaliza uma hipótese de relação, que deve ser confirmada manualmente pelo utilizador.

### 5.1 Conceito
O sistema **não agrega fisicamente ficheiros**.  
Apenas marca as pastas diárias com um identificador comum para sugerir possível relação entre elas.

Exemplo:

```text
08-13_Visita_Showroom__REV-0001
08-14_Visita_Showroom__REV-0001
```

### 5.2 Dry-run
```powershell
python .\scripts\apply_review_ids.py --min-confidence medium
```

### 5.3 Execução real
```powershell
python .\scripts\apply_review_ids.py --min-confidence medium --execute
```

### 5.4 Outputs gerados
```text
pipeline_state\manifests\review_id_manifest.json
pipeline_state\manifests\review_id_manifest.csv
pipeline_state\manifests\review_id_summary.json
```

---

## 6. Revisão manual do utilizador

Depois da aplicação dos IDs de revisão:

1. abrir as pastas com o mesmo `__REV-xxxx`
2. confirmar se pertencem ao mesmo evento
3. juntar manualmente os conteúdos, se fizer sentido
4. definir manualmente a nomenclatura final da pasta agregada

O sistema não faz:
- aprovação automática
- rejeição automática
- merge automático
- renomeação final automática da pasta consolidada

---

## 7. Fluxo completo resumido

```powershell
python .\scripts\scan_media.py
python .\scripts\summarize_registry.py
python .\scripts\cluster_temporal_preview.py
python .\scripts\build_move_plan_preview.py
python .\scripts\apply_simple_sort.py --execute
python .\scripts\process_review_folders.py --execute
python .\scripts\generate_cluster_semantics.py --model gemma3:latest --vision --max-images 1 --use-format --fallback-text-only --limit 100
python .\scripts\propose_multiday_links.py --max-gap-days 2
python .\scripts\apply_review_ids.py --min-confidence medium --execute
```

---

## 8. Recomendações operacionais

- usar `--limit 100` nas primeiras validações
- preferir `--max-images 1` para estabilidade
- tratar o sistema multi-dia como **sugestão**, não como decisão
- validar visualmente sempre que duas pastas partilhem o mesmo `__REV-xxxx`

---

## 9. Scripts em legado

Os seguintes scripts já não pertencem ao fluxo principal:

- `apply_move_plan.py`
- `apply_multiday_ids.py`

Devem ser considerados apenas legado/histórico.
