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
- criação ou atualização do registo de media
- escrita em `pipeline_state\registry\media_registry.jsonl`

Este passo é incremental: um ficheiro já indexado numa execução anterior
(mesmo tamanho e data de modificação) não volta a ser processado pelo
ExifTool nem re-hashado — o registo anterior é reaproveitado. Só ficheiros
novos ou alterados desde a última execução são processados de raiz, e
ficheiros removidos da origem deixam de aparecer no registo. Isto torna
execuções recorrentes muito mais rápidas à medida que a biblioteca cresce, e
protege o registo de uma interrupção a meio (a escrita é feita para um
ficheiro temporário e só substitui o registo existente no final, com sucesso).

Para forçar o reprocessamento completo de tudo (por exemplo, depois de
atualizar o ExifTool, ou se suspeitar de dados corrompidos):

```powershell
python .\scripts\scan_media.py --full-rescan
```

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

Um evento que atravesse a meia-noite (por exemplo, fotos entre as 23h e as
2h) mantém-se num único cluster, desde que o intervalo real entre fotos
consecutivas não ultrapasse o limite de confiança aplicável (4h para alta
confiança, 8h para média, 12h para baixa) — deixou de haver separação forçada
só por mudar o dia civil. Ficheiros sem hora real (só data) continuam a só
juntar-se a outros do mesmo dia civil, por segurança.

### 2.4 Plano de organização
```powershell
python .\scripts\build_move_plan_preview.py
```

Resultado esperado:
- proposta de organização por pastas
- ficheiros de preview e resumo

Antes de propor uma cópia, este passo verifica se o conteúdo do ficheiro (por
hash) já está presente em qualquer local dentro de `organized\`, usando o
índice descrito na secção 9. Se já estiver, o ficheiro é marcado como
`already_backed_up` e não entra no plano de cópia — isto evita duplicar
ficheiros já guardados, mesmo que o cluster de origem tenha sido renumerado
entre execuções.

### 2.5 Aplicação da organização simples
```powershell
python .\scripts\apply_simple_sort.py --execute
```

Resultado esperado:
- criação de pastas diárias automáticas
- envio de casos ambíguos para `_REVIEW`
- envio de casos não classificados para `_GENERAL`

### 2.6 Atalho: correr os passos 2.1–2.5 de uma vez

`run_pipeline.py` corre scan → resumo → clusterização → plano → aplicação
numa única chamada, na ordem correta, parando logo se algum passo falhar.
Não substitui o passo manual da secção 3.

```powershell
python .\scripts\run_pipeline.py
```

Sem `--execute`, tudo corre em preview (nada é copiado). Para aplicar a
organização a sério:

```powershell
python .\scripts\run_pipeline.py --execute
```

---

## 3. Tratamento das pastas `_REVIEW`

Depois de rever visualmente os conteúdos, o utilizador renomeia as pastas em `_REVIEW` com sufixos como:

- `_A` para aprovadas
- `_G` para general

Depois executa:

```powershell
python .\scripts\process_review_folders.py --execute
```

### Interpretação
- `_A` → a pasta é aceite e entra na organização normal
- `_G` → a pasta é enviada para a zona geral

### Nota sobre segurança do processamento
A data do evento é lida diretamente do nome da pasta `_REVIEW` (não é
recalculada a partir do cluster atual), por isso continua correta mesmo que
`cluster_temporal_preview.py` tenha sido executado novamente entretanto e
renumerado os clusters. Se o `cluster_id` da pasta já não existir no ficheiro
de clusters atual, ou apontar agora para um dia diferente, o script escreve
um aviso (`WARN_CLUSTER_ID_NOT_FOUND` / `WARN_CLUSTER_DAY_DRIFT`) no log — vale
a pena confirmar visualmente esses casos, embora o ficheiro continue a ser
processado para o dia correto.

---

## 4. Fluxo completo resumido

Passo a passo:

```powershell
python .\scripts\scan_media.py
python .\scripts\summarize_registry.py
python .\scripts\cluster_temporal_preview.py
python .\scripts\build_move_plan_preview.py
python .\scripts\apply_simple_sort.py --execute

# Rever manualmente a pasta _REVIEW e marcar cada pasta com _A ou _G

python .\scripts\process_review_folders.py --execute
```

Ou, usando o atalho da secção 2.6 para os primeiros cinco passos:

```powershell
python .\scripts\run_pipeline.py --execute

# Rever manualmente a pasta _REVIEW e marcar cada pasta com _A ou _G

python .\scripts\process_review_folders.py --execute
```

---

## 5. Revisão manual

A revisão manual serve para os casos em que o sistema não tem confiança suficiente para decidir sozinho.

O utilizador deve:
1. abrir as pastas em `_REVIEW`
2. verificar se o conteúdo faz sentido como conjunto coerente
3. marcar cada pasta com `_A` ou `_G`
4. correr novamente `process_review_folders.py`

---

## 6. Recomendações operacionais

- validar visualmente os casos colocados em `_REVIEW`
- usar sempre cópias dos ficheiros na fase inicial de testes
- confirmar o resultado final em `organized`
- evitar decisões automáticas em casos ambíguos

---

## 7. Estrutura lógica do processo

Em termos simples:

1. o sistema lê os ficheiros
2. tenta perceber a data de cada ficheiro
3. agrupa os ficheiros por proximidade temporal
4. organiza automaticamente o que é claro
5. separa para revisão o que é duvidoso
6. o utilizador decide manualmente os casos pendentes

---

## 8. Scripts em legado

Apenas um script é legado, e está em `scripts_old/` (não em `scripts/`):

- `apply_move_plan.py`

Os scripts `inspect_cluster_gps.py` e `propose_multiday_links_gps.py` são
auxiliares experimentais (uso manual, fora do fluxo principal descrito acima)
para sugerir ligações multi-dia por proximidade de GPS.

---

## 9. Índice de hashes de `organized\` (evitar cópias duplicadas)

`build_move_plan_preview.py` só sabe evitar propor cópias de ficheiros já
guardados se souber o que já está dentro de `organized\`. Essa informação
fica em `pipeline_state\registry\organized_hash_index.jsonl` e é atualizada
automaticamente por `apply_simple_sort.py --execute` e
`process_review_folders.py --execute` sempre que copiam ou movem um ficheiro.

Correr manualmente `build_organized_hash_index.py` (reconstrução completa por
hash de tudo o que está em `organized\`) é necessário em dois casos:

1. **Uma vez, na primeira utilização**, para indexar o que já foi organizado
   antes desta funcionalidade existir (incluindo pastas reorganizadas à mão).
2. **Sempre que reorganizar ficheiros manualmente dentro de `organized\`**
   (por exemplo, mover fotos para uma pasta com nome próprio) — essas
   alterações não passam pelos scripts do pipeline, por isso não ficam
   registadas automaticamente.

```powershell
python .\scripts\build_organized_hash_index.py
```

Não é necessário correr este script no fluxo normal e recorrente (secção 4) —
os dois scripts que copiam/movem ficheiros já mantêm o índice atualizado.
