"""Interface de terminal guiada para o MediaPipeline.

Um único ponto de entrada com um menu simples que corre os scripts pela
ordem certa e só pergunta o que é mesmo preciso (pasta de origem, nome do
lote). Não substitui nenhum script — cada um continua a poder ser corrido
diretamente com as suas próprias flags; isto só evita ter de decorar a
ordem, os nomes e os cuidados de cada passo.

Duas regras seguidas à risca, motivadas por incidentes reais desta sessão:
  - Nunca combinar num único botão/opção duas ações que só fazem sentido
    separadas (ex: exportar e limpar staging) — foi essa combinação que
    causou um re-export completo indesejado.
  - Nenhuma ação que apaga ou copia em massa corre sem confirmação escrita
    explícita ("sim"), mesmo que os dados já tenham sido pedidos antes.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import config

SCRIPTS_DIR = Path(__file__).resolve().parent
LAST_BATCH_NAME_FILE = config.PIPELINE_STATE / "menu_last_batch_name.txt"


def run(script_name: str, args: list[str]) -> int:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *args]
    print(f"\n$ {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode


def pause() -> None:
    input("\nPressiona Enter para voltar ao menu...")


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def ask_yes_no(prompt: str) -> bool:
    return input(f"{prompt} (escreve 'sim' para confirmar): ").strip().lower() == "sim"


def get_last_batch_name() -> str | None:
    if LAST_BATCH_NAME_FILE.exists():
        return LAST_BATCH_NAME_FILE.read_text(encoding="utf-8").strip() or None
    return None


def set_last_batch_name(name: str) -> None:
    LAST_BATCH_NAME_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_BATCH_NAME_FILE.write_text(name, encoding="utf-8")


def ask_batch_name() -> str:
    return ask("Nome do lote", default=get_last_batch_name())


def ensure_immich_api_key() -> bool:
    if os.environ.get("IMMICH_API_KEY"):
        return True
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "[System.Environment]::GetEnvironmentVariable('IMMICH_API_KEY','User')",
            ],
            capture_output=True, text=True, check=False,
        )
        key = result.stdout.strip()
    except OSError:
        key = ""
    if key:
        os.environ["IMMICH_API_KEY"] = key
        return True
    print(
        "\nFalta a IMMICH_API_KEY. Gera uma em Definições da conta -> API Keys, "
        "no Immich, e guarda-a com:\n"
        "  [System.Environment]::SetEnvironmentVariable('IMMICH_API_KEY','<chave>','User')\n"
        "Depois volta a tentar (pode ser preciso reabrir o terminal)."
    )
    return False


def export_already_completed(batch_name: str) -> bool:
    log_path = config.LOGS_DIR / f"export_from_immich_{batch_name}.log"
    if not log_path.exists():
        return False
    return "| END |" in log_path.read_text(encoding="utf-8", errors="replace")


def menu_producao() -> None:
    while True:
        print("\n=== Workflow principal (produção) ===")
        print("1. Correr scan + cluster + build + apply (preview, sem copiar)")
        print("2. Correr scan + cluster + build + apply (--execute, copia ficheiros)")
        print("3. Processar pastas revistas em _REVIEW (--execute)")
        print("0. Voltar")
        choice = input("> ").strip()

        if choice == "1":
            run("run_pipeline.py", [])
            pause()
        elif choice == "2":
            if ask_yes_no("Confirmas copiar ficheiros novos para organized/ agora?"):
                run("run_pipeline.py", ["--execute"])
            pause()
        elif choice == "3":
            if ask_yes_no("Confirmas que já reviste as pastas em _REVIEW e queres aplicar agora?"):
                run("process_review_folders.py", ["--execute"])
            pause()
        elif choice == "0":
            return
        else:
            print("Opção inválida.")


def menu_experimental() -> None:
    while True:
        print("\n=== Workflow experimental (Immich) ===")
        print("1. Preparar novo lote")
        print("2. [manual] Criar biblioteca e curar no Immich")
        print("3. Validar curadoria")
        print("4. Exportar lote")
        print("5. Limpar staging do lote (sem repetir o export)")
        print("6. [manual] Apagar biblioteca temporária")
        print("0. Voltar")
        choice = input("> ").strip()

        if choice == "1":
            source = ask("Pasta de origem")
            if not source:
                print("Pasta de origem é obrigatória.")
                pause()
                continue
            batch_name = ask_batch_name()
            if not batch_name:
                print("Nome do lote é obrigatório.")
                pause()
                continue
            set_last_batch_name(batch_name)
            run("prepare_batch.py", ["--source", source, "--batch-name", batch_name, "--execute"])
            pause()

        elif choice == "2":
            batch_name = ask_batch_name()
            print(
                "\n1. No Immich: Bibliotecas externas -> Nova biblioteca externa\n"
                f"2. Aponta para a pasta (no contentor): /mnt/batches_staging/{batch_name}/for_immich\n"
                "3. Analisar\n"
                "4. Cura os álbuns (sugestão de nome: AAAAMMDD - Nome do evento)\n"
                "   Fotos que não interessa arrumar como evento podem ficar sem álbum.\n"
            )
            pause()

        elif choice == "3":
            if not ensure_immich_api_key():
                pause()
                continue
            batch_name = ask_batch_name()
            run("validate_curation.py", ["--batch-name", batch_name])
            pause()

        elif choice == "4":
            if not ensure_immich_api_key():
                pause()
                continue
            batch_name = ask_batch_name()
            if ask_yes_no(f"Confirmas exportar o lote '{batch_name}' para organized_v2/ agora?"):
                set_last_batch_name(batch_name)
                run("export_from_immich.py", ["--batch-name", batch_name, "--execute"])
            pause()

        elif choice == "5":
            batch_name = ask_batch_name()
            if not export_already_completed(batch_name):
                print(
                    f"\nNão encontrei um export concluído no log para '{batch_name}' "
                    f"(pipeline_state/logs/export_from_immich_{batch_name}.log)."
                )
                if not ask_yes_no("Tens a certeza que este lote já foi exportado e queres limpar mesmo assim?"):
                    pause()
                    continue
            if ask_yes_no(
                f"Confirmas remover batches_staging/{batch_name}/ "
                "(o resultado do export já está em organized_v2/ e não é tocado)?"
            ):
                run("export_from_immich.py", ["--batch-name", batch_name, "--cleanup-only"])
            pause()

        elif choice == "6":
            print(
                "\nNo Immich: Bibliotecas externas -> (biblioteca deste lote) -> "
                "⋮ -> Eliminar.\nSó remove o índice do Immich, nunca ficheiros.\n"
            )
            pause()

        elif choice == "0":
            return
        else:
            print("Opção inválida.")


def menu_estado() -> None:
    print("\n=== Estado ===")

    staging_root = config.BATCHES_STAGING_ROOT
    lotes = sorted(p.name for p in staging_root.iterdir() if p.is_dir()) if staging_root.exists() else []
    if lotes:
        print(f"Lotes em batches_staging/: {', '.join(lotes)}")
    else:
        print("Nenhum lote em batches_staging/.")

    organized_v2 = config.ORGANIZED_V2_ROOT
    if organized_v2.exists():
        n_albuns = sum(1 for p in organized_v2.iterdir() if p.is_dir())
        n_ficheiros = sum(1 for p in organized_v2.rglob("*") if p.is_file())
        print(f"organized_v2/: {n_albuns} pastas, {n_ficheiros} ficheiros")
    else:
        print("organized_v2/ ainda não existe.")

    review_root = config.REVIEW_ROOT
    if review_root.exists():
        n_review = sum(1 for p in review_root.iterdir() if p.is_dir())
        print(f"_REVIEW/: {n_review} pastas por rever")

    pause()


def main() -> None:
    while True:
        print("\n=== MediaPipeline ===")
        print("1. Workflow principal (produção)")
        print("2. Workflow experimental (Immich)")
        print("3. Ver estado")
        print("4. Sair")
        choice = input("> ").strip()

        if choice == "1":
            menu_producao()
        elif choice == "2":
            menu_experimental()
        elif choice == "3":
            menu_estado()
        elif choice == "4":
            print("Até já.")
            return
        else:
            print("Opção inválida.")


if __name__ == "__main__":
    main()
