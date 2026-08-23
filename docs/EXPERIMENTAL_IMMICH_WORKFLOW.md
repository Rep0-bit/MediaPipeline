# Workflow experimental: curadoria no Immich + export por lote

> **Estado: experimental, branch `experiment/immich-curated-export`.**
> Não faz parte do workflow principal (ver [`WORKFLOW.md`](WORKFLOW.md)) e
> não altera nenhum script existente. Só passa a ser o workflow principal
> se, na prática, se provar melhor — decisão do utilizador, não automática.

## Porque existe

O workflow principal deteta os limites de evento por heurística temporal
(`cluster_temporal_preview.py`) e a revisão manual é feita a olhar
miniaturas em `_REVIEW/` no Explorer. Este workflow alternativo troca isso
por curadoria manual na interface do Immich (timeline, álbuns) — mais
agradável de usar — e depois **exporta** essa curadoria para uma pasta
final de backup.

É deliberadamente **one-shot por lote**, não contínuo: cada lote de fotos
novas passa uma vez por staging → curadoria → export, e fica arquivado. Não
há reprocessamento do mesmo lote mais tarde — isso evitaria o pipeline
principal e este workflow entrarem em conflito a reorganizar as mesmas
pastas ao longo do tempo.

O índice de hashes partilhado (`pipeline_state/registry/organized_hash_index.jsonl`,
o mesmo usado pelo workflow principal) garante que nenhum ficheiro é
processado duas vezes por qualquer um dos dois workflows.

---

## Configuração única (uma vez, antes do primeiro lote)

### 1. Novo bind mount no Immich

Adicionar ao `docker-compose.yml` do Immich (`C:\Tools\Immich\docker-compose.yml`),
no serviço `immich-server`, ao lado dos mounts existentes:

```yaml
    volumes:
      - ${UPLOAD_LOCATION}:/data
      - /etc/localtime:/etc/localtime:ro
      - ./photos:/mnt/photos:ro
      - ./organized:/mnt/organized:ro
      - ./batches_staging:/mnt/batches_staging:ro   # <- novo
      - ./immich-config.json:${IMMICH_CONFIG_FILE}:ro
```

Depois: `docker compose up -d` (recria o container `immich_server` para
aplicar o novo mount). Este caminho (`/mnt/batches_staging`) é uma
convenção fixa assumida pelo `export_from_immich.py` — não mudar o nome.

### 2. Gerar uma API key no Immich

No Immich: **Definições da conta → API Keys → New API Key**. Copiar a
chave (só é mostrada uma vez).

Definir como variável de ambiente **persistente** do utilizador Windows
(nunca escrever num ficheiro do repositório; um simples `$env:` só dura
para a janela de terminal atual):

```powershell
[System.Environment]::SetEnvironmentVariable("IMMICH_API_KEY", "<a-tua-chave>", "User")
```

Sessões de terminal já abertas (incluindo scripts em execução) não veem a
variável nova até serem reiniciadas. Se estiveres a correr os scripts a
partir de um terminal já aberto há algum tempo, ou de uma sessão que
reutiliza o mesmo processo, o mais simples é ler o valor diretamente do
registo no mesmo comando que precisa dele:

```powershell
$env:IMMICH_API_KEY = [System.Environment]::GetEnvironmentVariable("IMMICH_API_KEY", "User")
python .\scripts\export_from_immich.py --batch-name lote-2026-08 --execute
```

---

## Fluxo por lote

### 1. Preparar o lote

```powershell
python .\scripts\prepare_batch.py --source "C:\caminho\para\fotos\novas" --batch-name lote-2026-08 --execute
```

Separa os ficheiros em três pastas dentro de
`C:\Tools\Immich\batches_staging\lote-2026-08\`:

- `for_immich/` — sobreviventes (não estão em backup, não parecem
  documentos, não são duplicados dentro do lote). É esta pasta que vai ser
  curada no Immich.
- `documents/` — ficheiros que parecem documentos/cartões — não entram na
  curadoria, mas são guardados na mesma.
- `duplicates/` — cópias secundárias de conteúdo repetido dentro do
  próprio lote — idem.

Ficheiros já presentes no índice de hashes (já em `organized/` ou em
`organized_v2/` de um lote anterior) são ignorados por completo.

Sem `--execute`, mostra o que faria sem copiar nada.

### 2. Criar a biblioteca temporária no Immich

Manual, via interface do Immich:

1. **Bibliotecas externas → Criar biblioteca**, a apontar para
   `/mnt/batches_staging/lote-2026-08/for_immich`.
2. **Analisar** para indexar.

### 3. Curar

Na timeline do Immich, criar álbuns para cada evento identificado, com o
nome no formato **`AAAAMMDD - Nome do evento`** (por exemplo,
`20250718 - Aniversário da Maria`) — esse nome vira diretamente o nome da
pasta final, por isso a convenção de data no início mantém a ordenação
cronológica ao navegar em `organized_v2/` no Explorer.

Fotos que não interessa arrumar como evento ficam sem álbum — continuam a
ser guardadas (ver abaixo), só não como evento.

**Problema real encontrado no primeiro lote:** a timeline principal do
Immich mostra a biblioteca temporária do lote misturada com toda a
biblioteca já existente (`organized/`), por isso não dá para distinguir
visualmente "o que é novo" a olho. Duas formas de isolar:

- **Pesquisar pelo nome do ficheiro** (campo "Nome do ficheiro" na
  pesquisa). Cuidado: em nomes de screenshot do Android
  (`Screenshot_AAAA-MM-DD-HH-MM-SS-NN_<hash>.jpg`), o `<hash>` no fim
  **não é único por foto** — é um identificador da app/sessão de origem,
  partilhado por vários screenshots da mesma app ao longo do tempo.
  Pesquisar só por esse hash traz também screenshots antigos não
  relacionados com o lote atual.
- **Pesquisar pelo prefixo de data/hora** (a parte `AAAA-MM-DD-HH-MM` do
  nome) é fiável — é único ao segundo, e agrupa naturalmente screenshots
  tirados na mesma rajada (ex.: `Screenshot_2025-01-09-14-09` apanha os 5
  screenshots de uma sessão de ~17 segundos nesse dia).

Antes de curar, vale a pena listar os ficheiros que `prepare_batch.py`
pôs em `for_immich/` (`Get-ChildItem` ou `ls`) para teres a lista exata a
confirmar contra o que aparece na pesquisa.

### 4. Exportar

```powershell
python .\scripts\export_from_immich.py --batch-name lote-2026-08 --execute
```

Lê os álbuns via API do Immich e materializa o resultado em
`C:\Tools\Immich\organized_v2\`:

- Cada álbum → `organized_v2/<nome-do-álbum>/` (nome sanitizado para pasta
  válida, mas de resto igual ao nome do álbum).
- Ficheiros de `for_immich/` sem álbum → `organized_v2/_GERAL/lote-2026-08/`.
- `documents/` → `organized_v2/_GERAL/lote-2026-08/_DOCUMENTOS/` (cópia
  direta, nunca passou pelo Immich).
- `duplicates/` → `organized_v2/_GERAL/lote-2026-08/_DUPLICADOS/` (idem).

Sem `--execute`, mostra o que faria sem copiar nada. Correr duas vezes
seguidas com `--execute` não duplica nada (deteta ficheiros já copiados,
tal como `apply_simple_sort.py` no workflow principal).

### 5. Arrumar

Duas ações independentes, cada uma só acontece se for pedida
explicitamente — nunca automaticamente uma por causa da outra.

**A. Limpar `batches_staging/<lote>/` (script, opt-in explícito):**

```powershell
python .\scripts\export_from_immich.py --batch-name lote-2026-08 --execute --cleanup-staging
```

`--cleanup-staging` só tem efeito junto com `--execute` (falha com erro
claro se usada sozinha ou em dry-run — nunca apaga nada "por engano"). Só
remove a cópia intermédia em `batches_staging/`; o resultado já exportado
em `organized_v2/` não é tocado. Também não mexe em nada no Immich nem nos
ficheiros de origem do lote.

Se preferires fazer isto manualmente em vez de usar a flag, é seguro
remover `batches_staging/lote-2026-08/` à mão a qualquer momento depois de
confirmares o export.

**B. Apagar a biblioteca temporária no Immich (manual, sempre):**

**Bibliotecas externas → ⋮ → Eliminar.** Só remove o índice do Immich,
nunca ficheiros. Não há forma de automatizar isto com a API key atual
(scopes só de leitura, de propósito) — ver secção "Modo alternativo"
abaixo para uma forma de lidar com isto sem precisar de apagar a
biblioteca a cada lote.

---

## Modo alternativo: acumular vários lotes antes de exportar

O fluxo acima (secção "Fluxo por lote") assume uma biblioteca nova por
lote. Também é possível **acumular vários lotes na mesma biblioteca**,
para ires enriquecendo os mesmos álbuns à medida que chegam fotos novas,
e só exportar quando considerares a organização terminada:

1. Corre `prepare_batch.py` para cada lote novo, com nomes diferentes
   (`--batch-name lote1`, depois `--batch-name lote2`, ...). Cada um cria
   a sua própria pasta `batches_staging/<lote>/for_immich/`.
2. Na **mesma** biblioteca do Immich (criada uma vez), vai adicionando
   cada pasta nova em **Pastas → + Adicionar** — uma biblioteca pode ter
   várias pastas ao mesmo tempo (tal como a biblioteca principal já tem
   `/mnt/organized`). Cura os álbuns livremente, misturando conteúdo de
   vários lotes.
3. Quando terminares: corre `export_from_immich.py --batch-name <lote>
   --execute` **uma vez por cada lote** que acumulaste — o script filtra
   corretamente pelo `manifest.jsonl` de cada um, por isso não há risco de
   misturar ou duplicar mesmo com vários lotes na mesma biblioteca.
4. Para "limpar" a biblioteca sem precisar de tocar no Immich (nem de
   alargar a API key): usa `--cleanup-staging` (secção 5A) em cada lote já
   exportado. Isto apaga as pastas locais que a biblioteca estava a
   observar — na próxima análise (manual ou noturna), o Immich deteta que
   os ficheiros desapareceram do disco e marca-os offline sozinho, tal
   como aconteceu com os ficheiros de teste inválidos durante a
   verificação inicial (ver "O que foi testado" abaixo). A biblioteca fica
   "limpa" para a próxima ronda sem precisar de a apagar.

---

## O que foi testado

- `prepare_batch.py`: testado de ponta a ponta em ambiente sintético
  isolado, cobrindo os quatro casos — ficheiro novo, duplicado dentro do
  lote, documento, já em backup — com resultado correto em cada um, em
  dry-run e com `--execute`.
- `export_from_immich.py`: testado de ponta a ponta em ambiente sintético,
  simulando a resposta da API do Immich (sem chamadas reais), cobrindo os
  quatro destinos — álbum, sem álbum (`_GERAL`), documento, duplicado — com
  resultado correto em cada um. Confirmada a idempotência (correr duas
  vezes com `--execute` não duplica nem re-copia). Confirmado o erro claro
  quando `IMMICH_API_KEY` não está definida.
- **Testado também contra a instância real** (2026-08-23): biblioteca
  temporária `teste-verificacao` apontada para `/mnt/batches_staging/...`
  (com o bind mount novo aplicado via `docker compose up -d`), API key com
  scopes `album.read` + `asset.read`, um álbum real criado no Immich e
  exportado com sucesso via `export_from_immich.py --execute` — ficheiro
  corretamente traduzido do caminho do container para o caminho local,
  copiado para `organized_v2/<álbum>/`, e registado no índice de hashes
  partilhado. Biblioteca e ficheiros de teste removidos depois de
  confirmado.
  - Nota: os primeiros ficheiros de teste usados eram JPEGs inválidos
    (só cabeçalho, sem dados de imagem reais), o que fez a geração de
    miniaturas do Immich falhar (`VipsJpeg: ... unexpected EOI marker`) e
    os contadores da biblioteca mostrarem 0 — não era um problema do
    script. Resolvido ao usar PNGs válidos. Se os contadores de
    Fotos/Vídeos não subirem depois de "Analisar", confirmar nos logs do
    `immich_server` (`docker logs immich_server`) se há erros de
    `AssetGenerateThumbnails` antes de assumir que o scan falhou.
- **Primeiro lote real processado com sucesso** (2026-08-23,
  `lote-2026-08-23`): 89 ficheiros de origem, 72 já em backup (detetados
  pelo índice de hashes partilhado, incluindo 3 fotos de documento de
  identificação que nem chegaram a precisar do filtro de documentos), 17
  novos preparados. Curados em 2 álbuns (2 + 5 fotos); as 10 restantes
  foram para `_GERAL/lote-2026-08-23/`. Índice de hashes cresceu
  exatamente +17 (6415 → 6432) — confirma que nada foi duplicado nem
  reprocessado.
- **`--cleanup-staging` testado em ambiente sintético isolado**: confirmado
  que falha com erro claro quando usada sem `--execute`; confirmado que,
  combinada com `--execute`, remove `batches_staging/<lote>/` só depois de
  todas as cópias terem sido feitas com sucesso, sem tocar no resultado já
  em `organized_v2/`.

## Ficheiros deste workflow

- `scripts/prepare_batch.py`
- `scripts/export_from_immich.py`
- `scripts/config.py` — acrescenta `BATCHES_STAGING_ROOT`,
  `ORGANIZED_V2_ROOT`, `IMMICH_API_URL` (nenhum destes é usado pelo
  workflow principal)

Nenhum ficheiro existente do workflow principal foi alterado.
