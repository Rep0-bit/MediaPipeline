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