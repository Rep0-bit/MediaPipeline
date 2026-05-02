# Changelog

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
