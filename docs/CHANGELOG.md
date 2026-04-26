# Changelog

## v0.3-review-id-suggestions

### Estado
Extensão funcional **experimental** para sugestão de possíveis eventos multi-dia através da nomenclatura das pastas.

### Inclui
- aplicação de IDs `__REV-xxxx` a pastas sugeridas como relacionadas
- manifesto JSON e CSV com as propostas marcadas
- manutenção da estrutura diária original
- ausência de agregação física automática
- workflow de validação manual pelo utilizador

### Limitação atual
A funcionalidade encontra-se tecnicamente estável, mas a precisão semântica das sugestões multi-dia ainda não é suficientemente elevada para integração automática no workflow principal. Deve ser usada apenas como apoio à revisão manual.

### Scripts
- `scripts/apply_review_ids.py`

### Manifestos gerados
- `pipeline_state/manifests/review_id_manifest.json`
- `pipeline_state/manifests/review_id_manifest.csv`
- `pipeline_state/manifests/review_id_summary.json`

---

## v0.3-semantic-linking-calibrated

### Estado
Camada experimental funcional para enriquecimento semântico de clusters e proposta prudente de possíveis ligações multi-dia.

### Nota
Os testes mostraram que a infraestrutura funciona corretamente, mas que a utilidade operacional das sugestões multi-dia continua dependente de validação humana, devido à existência de falsos positivos em contextos visuais semelhantes.

### Inclui
- geração de nomes semânticos por cluster com Ollama
- tags, descrição curta e localização sugerida
- propostas multi-dia por pares
- penalização de títulos genéricos
- remoção de grupos agressivos por transitividade

### Scripts
- `scripts/generate_cluster_semantics.py`
- `scripts/propose_multiday_links.py`

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
