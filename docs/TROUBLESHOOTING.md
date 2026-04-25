# Troubleshooting

Este documento reúne os problemas mais comuns encontrados no MediaPipeline e respetivas formas de verificação.

---

## 1. O ambiente virtual não ativa no PowerShell

### Sintoma
Erro relacionado com `ExecutionPolicy` ou scripts desativados.

### Verificação
```powershell
Get-ExecutionPolicy -List
```

### Solução típica
Definir a política para o utilizador atual:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Depois reabrir o PowerShell e ativar novamente:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## 2. O `scan_media.py` corre, mas a metadata parece pobre

### Sintoma
Muitos ficheiros aparecem apenas com `FileModifyDate`.

### Interpretação
Isso não significa necessariamente erro. Pode simplesmente indicar que:
- o ficheiro não tem EXIF de captura incorporado
- a data teve de ser inferida por nome ou sistema de ficheiros

### Verificação
```powershell
python .\scripts\summarize_registry.py
```

---

## 3. As pastas `_REVIEW` ficam vazias

### Possível causa
O script `apply_simple_sort.py` pode ter colocado os ficheiros diretamente nas pastas automáticas ou `_GENERAL`, dependendo das regras atuais e do estado dos dados.

### Verificação
```powershell
Get-Content .\pipeline_state\registry\apply_simple_sort_summary.json
Get-Content .\pipeline_state\logs\apply_simple_sort.log -Tail 50
```

---

## 4. O `generate_cluster_semantics.py` falha com Ollama

### Verificações úteis
```powershell
ollama --version
Invoke-RestMethod http://localhost:11434/api/ps
```

### Teste manual simples
```powershell
$body = @{
  model = "gemma3:latest"
  stream = $false
  messages = @(
    @{
      role = "user"
      content = "Return valid JSON with keys title and tags for a family trip."
    }
  )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -ContentType "application/json" -Body $body
```

### Causa provável
- serviço Ollama não iniciado
- modelo não descarregado
- payload multimodal demasiado pesado
- memória insuficiente

---

## 5. O `propose_multiday_links.py` gera zero candidatos

### Possíveis causas
- poucos clusters no ficheiro de semântica
- clusters demasiado distintos
- scoring demasiado conservador
- `cluster_semantics.json` foi gerado com `--limit` demasiado baixo

### Verificação
```powershell
Get-Content .\pipeline_state\links\multiday_summary.json
```

### Ação recomendada
Regenerar semântica com mais clusters, por exemplo:

```powershell
python .\scripts\generate_cluster_semantics.py --model gemma3:latest --vision --max-images 1 --use-format --fallback-text-only --limit 100
python .\scripts\propose_multiday_links.py --max-gap-days 2
```

---

## 6. O `apply_review_ids.py` não renomeia pastas

### Verificar se o ficheiro de revisão existe
```powershell
Get-Item .\pipeline_state\links\multiday_review.csv
```

### Verificar se o plano de pastas existe
```powershell
Get-Item .\pipeline_state\registry\move_plan_preview.jsonl
```

### Verificar o resumo do manifesto
```powershell
Get-Content .\pipeline_state\manifests\review_id_summary.json
```

### Causa provável
- a confiança do candidato ficou abaixo de `--min-confidence`
- a pasta original já não existe no local esperado
- a pasta já foi renomeada anteriormente
- o cluster já não corresponde ao estado atual das pastas

---

## 7. Aparecem `folder_not_found` no `apply_review_ids.py`

### Interpretação
O script encontrou a proposta no CSV, mas não conseguiu localizar uma ou mais pastas correspondentes no diretório `organized`.

### Possíveis motivos
- a pasta foi apagada
- a pasta foi movida manualmente
- a pasta já foi renomeada de forma diferente
- o `move_plan_preview.jsonl` já não reflete o estado atual

### Verificação
```powershell
Get-ChildItem C:\Tools\Immich\organized -Directory -Recurse | Where-Object { $_.Name -like "*__REV-*" } | Select-Object FullName
```

---

## 8. Os acentos aparecem mal no PowerShell

### Sintoma
Texto como:
- `ReuniÃ£o`
- `NegÃ³cios`

### Causa
Problema de visualização da consola, não do ficheiro.

### Verificação correta
```powershell
Get-Content .\pipeline_state\semantics\cluster_semantics.json -Encoding UTF8 -Head 20
```

### Forçar UTF-8 na sessão
```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

---

## 9. O `git push` falha por falta de upstream

### Sintoma
Mensagem a indicar que a branch não tem upstream.

### Solução
```powershell
git push --set-upstream origin nome-da-branch
```

---

## 10. O projeto começa a ficar confuso com scripts antigos

### Recomendação
No workflow atual, usar apenas:

```text
scan_media.py
summarize_registry.py
cluster_temporal_preview.py
build_move_plan_preview.py
apply_simple_sort.py
process_review_folders.py
generate_cluster_semantics.py
propose_multiday_links.py
apply_review_ids.py
```

Os seguintes scripts devem ser tratados como legado:

```text
apply_move_plan.py
apply_multiday_ids.py
```
