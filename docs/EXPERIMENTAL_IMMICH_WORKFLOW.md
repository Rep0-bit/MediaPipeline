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

Definir como variável de ambiente (nunca escrever num ficheiro do
repositório):

```powershell
$env:IMMICH_API_KEY = "<a-tua-chave>"
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

### 5. Arrumar (manual)

Depois de confirmar que o export correu bem:

1. Apagar a biblioteca temporária no Immich (**Bibliotecas externas → ⋮ →
   Eliminar**) — só remove o índice do Immich, não toca em nenhum
   ficheiro.
2. Remover `batches_staging/lote-2026-08/` (opcional — já não é preciso,
   o conteúdo relevante já está em `organized_v2/`).

Não há automação para este passo nesta primeira versão.

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
- **Ainda não testado**: a chamada real à API do Immich (`/albums`,
  `/albums/{id}`) contra a instância real — requer uma API key gerada pelo
  utilizador e, idealmente, um álbum de teste pequeno antes de usar com um
  lote real. Fazer isso é o próximo passo antes de confiar neste workflow
  com fotos reais.

## Ficheiros deste workflow

- `scripts/prepare_batch.py`
- `scripts/export_from_immich.py`
- `scripts/config.py` — acrescenta `BATCHES_STAGING_ROOT`,
  `ORGANIZED_V2_ROOT`, `IMMICH_API_URL` (nenhum destes é usado pelo
  workflow principal)

Nenhum ficheiro existente do workflow principal foi alterado.
