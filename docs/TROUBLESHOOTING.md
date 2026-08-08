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

## 4. O `process_review_folders.py` não move as pastas como esperado

### Verificar se as pastas têm sufixo
As pastas em `_REVIEW` devem terminar com algo como:
- `_A`
- `_G`

### Verificação
```powershell
Get-ChildItem C:\Tools\Immich\organized\_REVIEW
```

### Causa provável
A pasta não foi renomeada corretamente antes de correr o script.

---

## 5. O `build_move_plan_preview.py` cria resultados estranhos

### Possíveis causas
- datas inconsistentes
- falta de metadata embebida
- nomes de ficheiro pouco informativos
- mistura de fotografias e ficheiros não relacionados na mesma pasta de entrada

### Verificação
```powershell
python .\scripts\summarize_registry.py
python .\scripts\cluster_temporal_preview.py
```

---

## 6. O resultado final em `organized` não parece coerente

### Verificação recomendada
1. abrir a pasta `organized`
2. verificar as pastas diárias
3. verificar o conteúdo de `_REVIEW`
4. verificar o conteúdo de `_GENERAL`

### Interpretação
Nem todos os erros são falhas do programa. Muitas vezes o problema vem de:
- datas ausentes
- ficheiros exportados por apps que alteraram metadata
- media misturado de várias origens

---

## 7. Os acentos aparecem mal no PowerShell

### Sintoma
Texto como:
- `ReuniÃ£o`
- `NegÃ³cios`

### Causa
Problema de visualização da consola, não do ficheiro.

### Verificação correta
```powershell
Get-Content .\pipeline_state\registry\media_registry.jsonl -Encoding UTF8 -Head 20
```

### Forçar UTF-8 na sessão
```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

---

## 8. O `git push` falha por falta de upstream

### Sintoma
Mensagem a indicar que a branch não tem upstream.

### Solução
```powershell
git push --set-upstream origin nome-da-branch
```

---

## 9. O projeto começa a ficar confuso com scripts antigos

### Recomendação
No workflow atual, usar apenas:

```text
scan_media.py
summarize_registry.py
cluster_temporal_preview.py
build_move_plan_preview.py
apply_simple_sort.py
process_review_folders.py
```

Scripts auxiliares experimentais (fora do fluxo principal, uso manual para
propor ligações multi-dia por proximidade de GPS):

```text
inspect_cluster_gps.py
propose_multiday_links_gps.py
```

Apenas um script é legado, e está em `scripts_old/` (não em `scripts/`):

```text
apply_move_plan.py
```
