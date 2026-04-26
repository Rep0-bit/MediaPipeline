# MediaPipeline

Pipeline local para organização de fotografias e vídeos por data/evento, com uma camada opcional de enriquecimento semântico e sugestão de possíveis ligações multi-dia.

## Objetivo

O projeto organiza media local em pastas diárias, separa casos que requerem revisão manual e, opcionalmente, sugere quando diferentes pastas diárias podem pertencer ao mesmo evento.

A lógica atual privilegia:

- segurança
- reversibilidade
- simplicidade operacional
- validação manual pelo utilizador

O sistema **não faz merge automático de ficheiros** entre pastas.  
Quando deteta possíveis ligações entre eventos diários, limita-se a marcar as pastas com um identificador comum do tipo:

```text
__REV-0001
```

Cabe ao utilizador confirmar visualmente se as pastas pertencem ao mesmo evento, juntar manualmente os elementos que entender e rever a nomenclatura final da pasta.

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
  generate_cluster_semantics.py
  propose_multiday_links.py
  apply_review_ids.py

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

### Camada semântica opcional e experimental
- `generate_cluster_semantics.py`  
  Usa Ollama para sugerir:
  - nome do evento
  - tags
  - descrição curta
  - pista de localização
  - keywords de possível continuidade multi-dia

- `propose_multiday_links.py`  
  Analisa os clusters semânticos e gera pares candidatos a pertencer ao mesmo evento multi-dia.

- `apply_review_ids.py`  
  Aplica IDs `__REV-xxxx` às pastas sugeridas como possivelmente pertencentes ao mesmo evento.

**Nota importante:** esta camada é experimental.  
Embora funcione corretamente do ponto de vista técnico, a precisão das sugestões multi-dia ainda não é suficientemente alta para uso automático no workflow principal. Deve ser usada apenas como apoio à revisão manual.

---

## Scripts obsoletos / legado

Os seguintes scripts deixaram de fazer parte do workflow principal:

- `apply_move_plan.py`
- `apply_multiday_ids.py`

Podem ser mantidos temporariamente no repositório por motivos de histórico, mas não devem ser usados no fluxo atual.

---

## Fluxo recomendado

## 1. Organização base

```powershell
python .\scripts\scan_media.py
python .\scripts\summarize_registry.py
python .\scripts\cluster_temporal_preview.py
python .\scripts\build_move_plan_preview.py
python .\scripts\apply_simple_sort.py --execute
python .\scripts\process_review_folders.py --execute
```

> A partir da etapa seguinte, o workflow entra numa camada opcional e experimental.  
> O resultado deve ser interpretado como sugestão de apoio à revisão humana, não como decisão automática.

## 2. Enriquecimento semântico

```powershell
python .\scripts\generate_cluster_semantics.py --model gemma3:latest --vision --max-images 1 --use-format --fallback-text-only --limit 100
```

## 3. Propostas de ligação multi-dia

```powershell
python .\scripts\propose_multiday_links.py --max-gap-days 2
```

## 4. Aplicação de IDs de revisão às pastas

```powershell
python .\scripts\apply_review_ids.py --min-confidence medium
python .\scripts\apply_review_ids.py --min-confidence medium --execute
```

## 5. Revisão manual pelo utilizador

Depois da execução, o utilizador:

1. identifica as pastas com o mesmo sufixo `__REV-xxxx`
2. confirma visualmente se pertencem ao mesmo evento
3. junta manualmente os ficheiros, se fizer sentido
4. renomeia manualmente a pasta final

---

## Convenção de nomenclatura multi-dia

### Sugestão de revisão
```text
__REV-0001
```

Exemplo:

```text
08-13_Visita_Showroom__REV-0001
08-14_Visita_Showroom__REV-0001
```

Isto significa apenas:

> “Estas pastas podem pertencer ao mesmo evento. Rever manualmente.”

Não significa que o evento esteja confirmado, nem que os conteúdos devam ser agregados automaticamente.

---

## Manifestos gerados

A camada de sugestão multi-dia gera os seguintes ficheiros:

```text
pipeline_state\manifests\review_id_manifest.json
pipeline_state\manifests\review_id_manifest.csv
pipeline_state\manifests\review_id_summary.json
```

Estes manifestos servem para:

- rastrear propostas marcadas
- manter consistência entre execuções
- reutilizar a mesma numeração `REV-xxxx`

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

- O projeto não depende de Immich para o scan interno; trabalha sobre pastas locais.
- O utilizador mantém sempre o controlo sobre as decisões finais.
- A camada Ollama é opcional.
- O merge físico de ficheiros entre pastas é intencionalmente manual.

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

Estado atual: **workflow funcional e estável para organização local**.  
A camada de enriquecimento semântico e de sugestões multi-dia está disponível como funcionalidade **opcional e experimental**, útil para exploração e apoio à revisão manual, mas ainda não suficientemente precisa para integração automática no workflow principal.
