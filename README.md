# MediaPipeline

Pipeline **local-first** para organização de fotografias e vídeos por evento, com apoio de metadata EXIF, heurísticas temporais e validação manual assistida.

---

## Objetivo

Este projeto organiza uma biblioteca multimédia local em três destinos principais:

- `organized\YYYY\MM-DD...` — eventos finais aprovados
- `organized\_REVIEW` — clusters que requerem validação manual
- `organized\_GENERAL` — duplicados, documentos e ficheiros sem classificação final de evento

O workflow foi desenhado para ser:

- **local-only**
- **não destrutivo**
- **reversível**
- **dry-run first**
- com **originais preservados** em `photos`

---

## Princípios do workflow

- Os ficheiros originais permanecem sempre em `photos`
- A organização é feita por **cópia**, nunca por remoção dos originais
- A metadata EXIF é prioritária face a inferências
- O sistema separa automaticamente:
  - eventos com confiança suficiente
  - casos para revisão manual
  - duplicados e documentos
- A revisão manual é feita por marcação de pastas com sufixos:
  - `_A` = aprovado
  - `_G` = enviar para General

---

## Estrutura de pastas

### Projeto

```text
C:\Tools\MediaPipeline\
├── .venv\
├── scripts\
├── pipeline_state\
│   ├── logs\
│   ├── registry\
│   └── cache\
├── .gitignore
└── README.md