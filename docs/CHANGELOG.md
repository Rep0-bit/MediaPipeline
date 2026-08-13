# Changelog

## v0.10-complete-workflow-guide

### Estado
Adiciona documentação de visão geral que liga o pipeline e o Immich num único fluxo; não altera nenhum script.

### Inclui
- Novo `docs/WORKFLOW.md`: ponto de entrada da documentação — diagrama (mermaid) e tabela resumo de todo o processo, desde as fotos no telemóvel até estarem visíveis no Immich. Explica explicitamente a fronteira entre as duas metades do processo (organização física, feita pelos scripts; consumo/visualização, feito pelo Immich) e responde a perguntas frequentes sobre essa fronteira.
- Nova imagem `docs/images/immich-05-jobs-queue.svg` (mockup de "Filas de tarefas", com base em captura de ecrã real partilhada pelo utilizador) e referência atualizada em `docs/IMMICH_LIBRARY_SETUP.md` — passo 3 agora explica que é normal ver picos temporários em "Gerar Miniaturas"/"Extrair Metadados" (não só em "Bibliotecas Externas") e que as contagens de Fotos/Vídeos podem subir antes de descer, com base em comportamento real observado nesta instalação.
- Nova secção sobre limpeza do lixo do Immich em `docs/IMMICH_LIBRARY_SETUP.md`.
- `README.md` aponta para `docs/WORKFLOW.md` como ponto de entrada recomendado.

---

## v0.9-immich-library-setup-guide

### Estado
Adiciona documentação operacional sobre a integração com o Immich; não altera nenhum script do pipeline.

### Inclui
- Novo `docs/IMMICH_LIBRARY_SETUP.md`: procedimento passo a passo, com mockups ilustrativos do painel de administração do Immich, para verificar e corrigir a configuração da External Library — deve apontar apenas para `organized/`, nunca para `photos/`.
- Nova secção "Integração com o Immich" em `README.md`, a explicar a expetativa de configuração e a apontar para o guia.
- Mockups em `docs/images/immich-*.svg` (SVG ilustrativo, não capturas reais).

### Nota
Motivado por uma configuração incorreta encontrada e corrigida nesta instalação: a External Library do Immich estava a apontar tanto para `photos/` (despejo bruto) como para `organized/` (resultado curado), duplicando cada ficheiro no índice do Immich e tornando a triagem deste pipeline sem efeito prático na biblioteca visível. Corrigido diretamente na base de dados do Immich (`library.importPaths`); cópia de segurança do estado anterior em `pipeline_state/immich_backup/` (fora do controlo de versões).

Os mockups foram revistos numa correção de seguimento depois de o utilizador
confirmar, com capturas de ecrã reais, que a interface real está em
português e usa uma estrutura de menu diferente da assumida inicialmente
(ex.: "Bibliotecas externas" como item próprio no menu, não "Definições").

---

## v0.8-midnight-boundary-clustering

### Estado
Corrige um caso de over-splitting na clusterização temporal, sem alterar os limites de confiança nem a lógica de deteção de timestamp.

### Inclui
- `cluster_temporal_preview.py` deixa de forçar uma separação de cluster só por o timestamp seguinte cair num dia civil diferente. Passa a aplicar o mesmo critério de sempre (gap em horas vs. limite de confiança — 4h/8h/12h) também através da fronteira da meia-noite, em vez de um corte incondicional por data.
- Ficheiros com precisão apenas de data (sem hora real) mantêm o comportamento anterior por segurança: só se juntam a outros do mesmo dia civil, porque não é possível calcular um gap fiável sem hora.

### Nota
Testado com 8 cenários sintéticos (gap pequeno/grande atravessando meia-noite, gap pequeno/grande no mesmo dia, precisão só-data atravessando/não atravessando meia-noite, precisão mista, timestamp em falta) e verificado contra o registry real: 660 → 651 clusters (9 fusões). Inspecionado um caso em detalhe (`event-0151`, fotos de WhatsApp entre a noite de 6 e a manhã de 7 de dezembro de 2024) para confirmar que a fusão resulta de uma cadeia de gaps individualmente válidos, não de uma fusão indevida.

---

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
