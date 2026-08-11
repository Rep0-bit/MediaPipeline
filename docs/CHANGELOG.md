# Changelog

## v0.7-incremental-scan

### Estado
Torna `scan_media.py` incremental e resistente a interrupções, sem alterar o formato das restantes etapas do workflow.

### Inclui
- `scan_media.py` passa a reaproveitar o registo de ficheiros já indexados cujo tamanho e data de modificação não mudaram desde a última execução, evitando reprocessamento (ExifTool + hash) desnecessário à medida que a biblioteca cresce.
- Novo campo `mtime_epoch` em cada registo, usado (junto com `size_bytes`) para detetar ficheiros alterados.
- Ficheiros removidos da pasta de origem deixam de aparecer no registo depois de uma nova execução.
- Escrita atómica do registo (ficheiro temporário + `os.replace` no final) — uma interrupção a meio da execução já não destrói o registo existente, ao contrário do comportamento anterior (que truncava o ficheiro no início e escrevia progressivamente).
- Nova flag `--full-rescan` para forçar o reprocessamento completo quando necessário (ex.: depois de atualizar o ExifTool).

### Scripts
- `scripts/scan_media.py`

### Nota
Registos escritos pela versão anterior do script não têm `mtime_epoch`, por isso a primeira execução após esta atualização reprocessa a biblioteca inteira uma única vez (custo de migração); execuções seguintes já beneficiam da reutilização incremental. Testado com cenários sintéticos (ficheiro inalterado, alterado, novo e removido) e verificado contra o registry real (7364 ficheiros).

---

## v0.6-pipeline-orchestrator

### Estado
Adiciona um atalho de execução sobre o workflow estabilizado em v0.5, sem alterar a lógica de nenhum passo individual.

### Inclui
- `scripts/run_pipeline.py`: corre scan → resumo → clusterização → plano → aplicação numa única chamada, na ordem correta, parando imediatamente se algum passo falhar. Não inclui `process_review_folders.py`, que continua a exigir revisão manual das pastas `_REVIEW` antes de ser corrido.
- Sem `--execute`, todos os passos correm em preview/dry-run (o comportamento por omissão de `apply_simple_sort.py`); com `--execute`, a flag é propagada apenas a esse passo.

### Scripts
- `scripts/run_pipeline.py`

### Nota
Testado de ponta a ponta em ambiente isolado (incluindo `--execute` real e uma segunda execução para confirmar que ficheiros já copiados são corretamente ignorados via o índice de hashes) e em modo preview contra o registry real.

---

## v0.5-consistency-and-safety-fixes

### Estado
Correções de consistência e de segurança sobre o workflow base estabilizado em v0.4, sem alterar a lógica de clusterização.

### Inclui
- correção dos scripts GPS (`inspect_cluster_gps.py`, `propose_multiday_links_gps.py`), que liam GPS em campos inexistentes e nunca encontravam nada; passam a ler `exif.gps.latitude`/`exif.gps.longitude`
- centralização de todos os paths hardcoded (`C:\Tools\MediaPipeline`, `C:\Tools\Immich`) em `scripts/config.py`
- correção de `process_review_folders.py`: a data do evento passa a ser lida do nome da pasta `_REVIEW` em vez de recalculada a partir de um `cluster_id` que pode já não corresponder ao mesmo cluster (renumeração entre execuções); avisos `WARN_CLUSTER_ID_NOT_FOUND`/`WARN_CLUSTER_DAY_DRIFT` tornam o desvio visível em vez de silencioso
- índice de hashes de `organized/` (`scripts/hash_index.py`, `scripts/build_organized_hash_index.py`), consultado por `build_move_plan_preview.py` para nunca propor a cópia de um ficheiro cujo conteúdo já esteja em qualquer local dentro de `organized/`, independentemente do cluster ou nome de pasta atual
- `.gitattributes` (`* text=auto`) para eliminar o churn de CRLF/LF nos diffs
- correção de referências a scripts inexistentes em `docs/TROUBLESHOOTING.md` e `docs/GUIA_UTILIZACAO.md`

### Scripts
- `scripts/scan_media.py`
- `scripts/summarize_registry.py`
- `scripts/cluster_temporal_preview.py`
- `scripts/build_move_plan_preview.py`
- `scripts/apply_simple_sort.py`
- `scripts/process_review_folders.py`
- `scripts/build_organized_hash_index.py`
- `scripts/config.py`, `scripts/hash_index.py` (suporte partilhado)

### Nota
`inspect_cluster_gps.py` e `propose_multiday_links_gps.py` continuam auxiliares e experimentais, fora do fluxo principal — apenas foram corrigidos, não promovidos a passo automático.

---

## v0.4-base-workflow-only

### Estado
Workflow estabilizado e simplificado para organização local por data com revisão manual.

### Inclui
- scan de media
- resumo do registo
- clusterização temporal
- preview de organização
- organização automática por data
- separação entre `_REVIEW` e `_GENERAL`
- revisão manual por sufixos `_A` e `_G`

### Scripts
- `scripts/scan_media.py`
- `scripts/summarize_registry.py`
- `scripts/cluster_temporal_preview.py`
- `scripts/build_move_plan_preview.py`
- `scripts/apply_simple_sort.py`
- `scripts/process_review_folders.py`

### Nota
Foram removidas do workflow principal as tentativas de enriquecimento semântico e de agregação multi-day, por não apresentarem precisão suficiente para uso operacional.

---

## v0.3-review-id-suggestions

### Estado
Funcionalidade experimental de sugestão de possíveis eventos multi-day através da nomenclatura das pastas.

### Inclui
- aplicação de IDs `__REV-xxxx` a pastas sugeridas como relacionadas
- manifesto JSON e CSV com as propostas marcadas
- manutenção da estrutura diária original
- ausência de agregação física automática

### Nota
Esta funcionalidade deixou de integrar o workflow principal.

---

## v0.3-semantic-linking-calibrated

### Estado
Camada experimental de enriquecimento semântico de clusters e proposta prudente de possíveis ligações multi-day.

### Inclui
- geração de nomes semânticos por cluster com Ollama
- tags, descrição curta e localização sugerida
- propostas multi-day por pares

### Nota
Os testes mostraram utilidade limitada e ocorrência de falsos positivos. Esta funcionalidade deixou de integrar o workflow principal.

---

## v0.2-full-workflow-stable

### Estado
Workflow integral validado para organização local com separação entre automático, revisão e general.

### Inclui
- organização base por data
- clusters temporais
- pastas `_REVIEW`
- pastas `_GENERAL`
- revisão por sufixos definida manualmente

### Scripts
- `scripts/scan_media.py`
- `scripts/summarize_registry.py`
- `scripts/cluster_temporal_preview.py`
- `scripts/build_move_plan_preview.py`
- `scripts/apply_simple_sort.py`
- `scripts/process_review_folders.py`

---

## v0.1-foundation

### Estado
Base inicial do pipeline local de catalogação e preview de organização.

### Inclui
- scan de media
- resumo do registo
- pré-clusterização temporal
- preview de move plan
