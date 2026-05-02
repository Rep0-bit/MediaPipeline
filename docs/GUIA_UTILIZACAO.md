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

---

## 4. Fluxo completo resumido

```powershell
python .\scripts\scan_media.py
python .\scripts\summarize_registry.py
python .\scripts\cluster_temporal_preview.py
python .\scripts\build_move_plan_preview.py
python .\scripts\apply_simple_sort.py --execute

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

Os seguintes scripts já não pertencem ao fluxo principal e não devem ser usados:

- `apply_move_plan.py`
- `apply_review_ids.py`
- `propose_multiday_links.py`
- `generate_cluster_semantics.py`
