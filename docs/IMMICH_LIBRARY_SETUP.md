# Configuração da Biblioteca Externa no Immich

> As imagens deste guia são mockups ilustrativos, redesenhados a partir de
> capturas de ecrã reais desta instalação (Immich v3.1.0, interface em
> português) — não são capturas diretas, mas seguem de perto o layout e a
> terminologia reais.

## Porque é que este guia existe

Por omissão, é fácil a Biblioteca Externa do Immich acabar a apontar tanto
para `photos/` (o despejo bruto do telemóvel, sem qualquer triagem) como
para `organized/` (o resultado curado por este pipeline). Foi exatamente
isto que aconteceu nesta instalação e que motivou este guia.

Quando isto acontece, dois problemas surgem ao mesmo tempo:

- O Immich mostra tudo o que está em `photos/` sem qualquer triagem —
  capturas de ecrã, documentos, quase-duplicados — exatamente o conteúdo que
  este pipeline existe para filtrar antes de ser considerado "backup real".
- Cada ficheiro que passa pelo pipeline e chega a `organized/` fica indexado
  **duas vezes** no Immich: uma vez a partir de `photos/` (original) e outra
  a partir de `organized/` (a cópia curada).

A correção é simples, mas não é óbvia se não se souber onde procurar: em
**Pastas**, a biblioteca só deve ter `/mnt/organized` — nunca `/mnt/photos`.

---

## Passo 1 — Abrir "Bibliotecas externas"

No menu lateral de administração, clicar em **Bibliotecas externas**
(segundo item, ícone de estante) — não em "Definições". A secção
"Biblioteca Externa" dentro de Definições controla o comportamento global
(análise periódica, etc.), não os caminhos de uma biblioteca específica.

![Página "Bibliotecas externas" do Immich, mostrando a tabela com a biblioteca "New External Library" e uma anotação a indicar para clicar no nome para abrir os detalhes](images/immich-01-external-libraries-list.svg)

Clicar no nome **New External Library** para abrir os detalhes.

---

## Passo 2 — Verificar e remover `/mnt/photos`

Na página de detalhes da biblioteca, o painel **Pastas** lista os caminhos
indexados. Se mostrar `/mnt/photos` **e** `/mnt/organized` em conjunto, é
este o problema a corrigir:

![Página de detalhes da biblioteca mostrando o painel "Pastas" com /mnt/photos (a vermelho, marcado para remover) e /mnt/organized (a verde, para manter), com anotação a explicar porquê](images/immich-02-edit-library-before.svg)

1. Clicar no ícone de caixote do lixo 🗑 ao lado de `/mnt/photos`.
2. Confirmar que `/mnt/organized` continua na lista.

![Painel "Pastas" depois da correção, mostrando apenas /mnt/organized, com confirmação visual de que a configuração está correta](images/immich-03-edit-library-after.svg)

**Não remover `/mnt/organized`** — é esse o caminho que deve ficar. O painel
**Padrão de exclusão** ao lado (`**/@eaDir/**`, `**/.stfolder/**`, etc.) não
precisa de ser alterado.

---

## Passo 3 — Forçar uma nova análise

Remover `/mnt/photos` de **Pastas** **não remove imediatamente** os
ficheiros já indexados a partir desse caminho — isso só acontece na próxima
análise da biblioteca.

![Botão "Analisar" destacado no topo da página de detalhes, com o progresso da tarefa em "Filas de tarefas" e nota sobre a análise noturna automática](images/immich-04-scan-trigger.svg)

1. No topo da página da biblioteca, clicar em **Analisar** para forçar a
   análise de imediato.
2. Acompanhar o progresso em **Filas de tarefas** (menu lateral).

Se não quiser fazer nada manualmente, o Immich corre isto de qualquer forma
todas as noites à meia-noite — ver `library.scan.cronExpression` em
`immich-config.json`.

---

## O que esperar depois da análise

- Os ficheiros indexados a partir de `/mnt/photos` passam a **offline** no
  Immich e são movidos para o lixo (retenção de 30 dias antes de apagar
  definitivamente — configurável em `immich-config.json` → `trash.days`).
- **Os ficheiros originais em disco não são tocados.** A biblioteca está
  montada como só-leitura (`:ro` em `docker-compose.yml`), por isso o Immich
  só pode alterar o seu próprio índice, nunca os ficheiros de origem.
- As contagens de **Fotos** e **Vídeos** nos cartões do topo da página
  descem para refletir apenas o conteúdo de `/mnt/organized`.
- O que sobra no Immich passa a corresponder exatamente ao resultado curado
  deste pipeline, incluindo o histórico de reconhecimento facial
  (pessoas/rostos), que se mantém para os ficheiros que também existem em
  `organized/`.

---

## Nota histórica

Esta configuração incorreta (`/mnt/photos` **e** `/mnt/organized` na mesma
biblioteca) foi identificada e corrigida diretamente na base de dados do
Immich em 2026-08-11, depois de se confirmar que a biblioteca ativa tinha
14 732 ativos indexados — cerca do dobro dos ~7 364 ficheiros reais — porque
cada ficheiro estava a ser contado duas vezes. Existe uma cópia de
segurança do estado anterior da tabela `library` em
`pipeline_state/immich_backup/` (fora do controlo de versões, local a cada
instalação). A correção foi confirmada visualmente na interface a
2026-08-12: o painel **Pastas** já só mostra `/mnt/organized`.

Este guia existe para o caso de ser necessário repetir o processo — por
exemplo, depois de recriar a biblioteca, reinstalar o Immich, ou configurar
uma nova instalação.
