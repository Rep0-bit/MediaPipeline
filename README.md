# MediaPipeline

Pipeline local para organização de fotografias e vídeos por data, com separação entre organização automática, revisão manual e pasta geral.

## Objetivo

O projeto organiza ficheiros de media copiados para o computador, tentando agrupá-los por data e por conjunto temporal coerente.

A lógica atual privilegia:

- simplicidade
- previsibilidade
- controlo manual
- reversibilidade

O sistema não faz interpretação semântica do conteúdo das imagens nem tenta agregar automaticamente eventos de vários dias. O foco está na organização base dos ficheiros e na revisão manual dos casos duvidosos.

---

## Estrutura principal do projeto

```text
scripts/
  scan_media.py
  summarize_registry.py
  cluster_temporal_preview.py
  build_move_plan_preview.py
  apply_simple_sort.py
  process_review_folders.py

docs/
  GUIA_UTILIZACAO.md
  TROUBLESHOOTING.md
  CHANGELOG.md
```

---

## Scripts ativos

### Organização base
- `scan_media.py`  
  Faz o scan dos ficheiros de media e cria o registo base.

- `summarize_registry.py`  
  Gera um resumo estatístico do registo.

- `cluster_temporal_preview.py`  
  Enriquece timestamps e gera clusters temporais.

- `build_move_plan_preview.py`  
  Propõe a organização-alvo das pastas.

- `apply_simple_sort.py`  
  Aplica a organização base em:
  - pastas diárias automáticas
  - `_REVIEW`
  - `_GENERAL`

- `process_review_folders.py`  
  Processa as pastas em `_REVIEW` com base nos sufixos definidos manualmente pelo utilizador.

---

## Fluxo recomendado

### 1. Organização base

```powershell
python .\scripts\scan_media.py
python .\scripts\summarize_registry.py
python .\scripts\cluster_temporal_preview.py
python .\scripts\build_move_plan_preview.py
python .\scripts\apply_simple_sort.py --execute
python .\scripts\process_review_folders.py --execute
```

---

## Pastas principais de saída

### Pastas diárias
O sistema cria automaticamente pastas por data, por exemplo:

```text
07-28
07-29
08-11
```

### `_REVIEW`
Recebe ficheiros ou conjuntos de ficheiros que precisam de validação manual.

### `_GENERAL`
Recebe ficheiros que não devem ser tratados como evento específico.

---

## Revisão manual

Depois de rever visualmente as pastas dentro de `_REVIEW`, o utilizador pode classificá-las com sufixos como:

- `_A` → pasta aceite como válida
- `_G` → pasta a enviar para a zona geral

Depois, o script `process_review_folders.py` trata essa decisão e move os conteúdos para o local adequado.

---

## Dependências e ambiente

O projeto foi concebido para execução local em Windows com Python em ambiente virtual.

Exemplo de ativação:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## Notas importantes

- O projeto trabalha sobre pastas locais.
- O utilizador mantém o controlo sobre as decisões finais.
- A revisão manual continua a ser parte essencial do processo.
- O foco atual está na estabilidade da organização base.

---

## Ficheiros que não devem ser versionados

Tipicamente devem ficar fora do Git:

```text
.venv/
pipeline_state/
photos/
organized/
```

---

## Estado do projeto

Estado atual: **workflow funcional e estável para organização local por data com revisão manual**.
