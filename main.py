"""
Pipeline completo — roda com: python main.py

Etapas:
  0. Detecta os Excel da Natura e converte para CSV (base.csv / BASE2/base_falta.csv)
  1. Extrai pedidos filtrados por transportadora Dias
  2. Baixa relatórios do Diaslog (relatorionotas.csv e BASE2/relatorionotas_falta.csv)
  3. Roda limpeza_falta.py → BASE2/base_falta_pronta.csv (copiado para raiz)
  4. Roda limpeza.py → base_pronta.csv + tabelas de justificativas
  5. Git commit e push
"""
import asyncio
import glob
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path


import pandas as pd

from automacao_diaslog import baixar_relatorio_notas

ROOT = Path(__file__).parent
BASE2 = ROOT / "BASE2"

# Pastas onde os Excel da Natura costumam chegar
_PASTAS_BUSCA = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
]

# Transportadoras válidas para faltas (mesmo critério do limpeza_falta.py)
_TRANSPORTADORAS_FALTAS = {
    "MM DELIVERY TRANSPORTES LTDA",
    "M D  DELIVERY TRANSPORTES EIRELI",
    "SAFE ADMINISTRACAO LTDA",
    "DIAS ENTREGADORA LTDA",
    "M. D. DELIVERY TRANSPORTES EIRELI",
    "M. D. DELIVERY TRANSPORTES LTDA",
    "M D DELIVERY TRANSPORTES EIRELLI",
    "M D DELIVERY TRANSPORTES EIRELI",
    "MD DELIVERY",
    "MD DELIVERY TRANSPORTES EIRELI",
    "MM DELIVERY",
}


# ---------------------------------------------------------------------------
# ETAPA 0 — Detectar e converter os Excel da Natura
# ---------------------------------------------------------------------------

def _encontrar_excel(padrao: str) -> Path:
    """Busca o Excel mais recente que casa com o padrão nas pastas conhecidas."""
    candidatos = []
    for pasta in _PASTAS_BUSCA:
        candidatos += glob.glob(str(pasta / padrao))
    if not candidatos:
        raise FileNotFoundError(
            f"Nenhum arquivo '{padrao}' encontrado em:\n"
            + "\n".join(f"  {p}" for p in _PASTAS_BUSCA)
            + "\nVerifique o nome do arquivo ou informe o caminho manualmente."
        )
    return Path(max(candidatos, key=os.path.getmtime))


def _excel_para_csv_base(origem: Path, destino: Path) -> None:
    print(f"  → Convertendo: {origem.name}")
    df = pd.read_excel(origem, dtype=str)
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, sep=";", index=False, encoding="utf-8-sig")
    print(f"  ✅ Salvo: {destino} ({len(df)} linhas)")


def _etapa_converter_bases() -> None:
    print("\n=== ETAPA 0 — Conversão dos Excel da Natura ===")

    excel_danos = _encontrar_excel("Base_R*.xlsx")
    _excel_para_csv_base(excel_danos, ROOT / "base.csv")

    excel_faltas = _encontrar_excel("PPM Falta*.xlsx")
    _excel_para_csv_base(excel_faltas, BASE2 / "base_falta.csv")


# ---------------------------------------------------------------------------
# Extrair pedidos filtrados
# ---------------------------------------------------------------------------

def _ler_csv(caminho: Path) -> pd.DataFrame:
    for enc in ("utf-8", "latin1"):
        for sep in (";", "\t", ","):
            try:
                df = pd.read_csv(caminho, sep=sep, encoding=enc, low_memory=False, dtype=str)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue
    raise ValueError(f"Não foi possível ler {caminho}")


def _limpar_pedido(serie: pd.Series) -> list[str]:
    serie = serie.dropna().astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    return [p for p in serie.unique() if p and p.upper() not in ("NAN", "NONE", "")]


def _extrair_pedidos_danos() -> list[str]:
    df = _ler_csv(ROOT / "base.csv")
    df = df[df["transportadora"].astype(str).str.contains("DIAS", case=False, na=False)]
    pedidos = _limpar_pedido(df["pedido"])
    print(f"  → {len(pedidos)} pedidos Dias únicos (danos)")
    return pedidos


def _extrair_pedidos_faltas() -> list[str]:
    df = _ler_csv(BASE2 / "base_falta.csv")
    df["nome_transportadora"] = df["nome_transportadora"].astype(str).str.strip()
    df = df[df["nome_transportadora"].isin(_TRANSPORTADORAS_FALTAS)]
    pedidos = _limpar_pedido(df["nm_pedido"])
    print(f"  → {len(pedidos)} pedidos Dias únicos (faltas)")
    return pedidos


# ---------------------------------------------------------------------------
# ETAPA 1 — Baixar relatórios no Diaslog
# ---------------------------------------------------------------------------

async def _etapa_relatorios(headless: bool) -> None:
    print("\n=== ETAPA 1 — Relatórios Diaslog ===")

    print("\n[Danos]")
    await baixar_relatorio_notas(
        pedidos=_extrair_pedidos_danos(),
        destino=str(ROOT / "relatorionotas.csv"),
        headless=headless,
    )

    print("\n[Faltas]")
    await baixar_relatorio_notas(
        pedidos=_extrair_pedidos_faltas(),
        destino=str(BASE2 / "relatorionotas_falta.csv"),
        headless=headless,
    )


# ---------------------------------------------------------------------------
# ETAPA 2 — Limpeza faltas
# ---------------------------------------------------------------------------

def _etapa_limpeza_faltas() -> None:
    print("\n=== ETAPA 2 — Limpeza Faltas ===")
    subprocess.run([sys.executable, "limpeza_falta.py"], cwd=str(BASE2), check=True)
    # Copia para a raiz os arquivos que o dashboard (dados.py) lê de lá
    for nome in ("base_falta_pronta.csv", "relatorionotas_falta.csv"):
        src = BASE2 / nome
        dst = ROOT / nome
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  ✅ Copiado para raiz: {nome}")
        else:
            print(f"  ⚠️  Não encontrado em BASE2: {nome}")


# ---------------------------------------------------------------------------
# ETAPA 3 — Limpeza danos + justificativas
# ---------------------------------------------------------------------------

def _etapa_limpeza_danos(data_inicio: str, data_fim: str) -> None:
    print("\n=== ETAPA 3 — Limpeza Danos + Justificativas ===")
    subprocess.run(
        [sys.executable, "limpeza.py"],
        cwd=str(ROOT),
        input=f"{data_inicio}\n{data_fim}\n",
        text=True,
        check=True,
    )


# ---------------------------------------------------------------------------
# ETAPA 4 — Gerar Excel de tratativas (Danos + Faltas em abas separadas)
# ---------------------------------------------------------------------------

_ONEDRIVE = Path(os.environ.get("OneDrive", Path.home() / "OneDrive"))
_NOME_EXCEL = "tratativas.xlsx"   # nome fixo → link do OneDrive nunca muda


def _etapa_gerar_excel_tratativas() -> None:
    print("\n=== ETAPA 4 — Gerando Excel de Tratativas ===")

    arquivo_danos  = ROOT / "tabela_justificativas_danos.csv"
    arquivo_faltas = ROOT / "tabela_justificativas_faltas.csv"

    if not arquivo_danos.exists() or not arquivo_faltas.exists():
        print("  ⚠️  Arquivos de justificativas não encontrados. Pulando etapa.")
        return

    df_danos  = _ler_csv(arquivo_danos)
    df_faltas = _ler_csv(arquivo_faltas)

    # Salva na pasta outputs/data/ local
    hoje = date.today().strftime("%d-%m-%Y")
    pasta_saida = ROOT / "outputs" / hoje
    pasta_saida.mkdir(parents=True, exist_ok=True)
    destino_local = pasta_saida / _NOME_EXCEL

    # Salva também direto no OneDrive (sincroniza automaticamente)
    destino_onedrive = _ONEDRIVE / _NOME_EXCEL

    # Salva na pasta outputs/data/ local (sempre)
    with pd.ExcelWriter(str(destino_local), engine="openpyxl") as writer:
        df_danos.to_excel(writer,  sheet_name="Danos",  index=False)
        df_faltas.to_excel(writer, sheet_name="Faltas", index=False)
    print(f"  ✅ Salvo localmente: {destino_local}")

    # Salva no OneDrive (só se a pasta existir — funciona apenas no PC do Ícaro)
    if _ONEDRIVE.exists():
        with pd.ExcelWriter(str(destino_onedrive), engine="openpyxl") as writer:
            df_danos.to_excel(writer,  sheet_name="Danos",  index=False)
            df_faltas.to_excel(writer, sheet_name="Faltas", index=False)
        print(f"  ✅ Salvo no OneDrive: {destino_onedrive}")
        print(f"  🌐 Dashboard atualizado automaticamente.")
    else:
        print(f"\n  ℹ️  OneDrive não encontrado neste PC.")
        print(f"  📎 Envie o arquivo abaixo para o Ícaro subir no OneDrive:")
        print(f"     {destino_local}")


# ---------------------------------------------------------------------------
# ETAPA 5 — Exportar arquivos finais para pasta com data
# ---------------------------------------------------------------------------

# Arquivos gerados pelo pipeline que devem ser exportados
_ARQUIVOS_SAIDA = [
    ROOT / "base_pronta.csv",
    ROOT / "base_falta_pronta.csv",
    ROOT / "tabela_justificativas_danos.csv",
    ROOT / "tabela_justificativas_faltas.csv",
    ROOT / "relatorionotas.csv",
    BASE2 / "relatorionotas_falta.csv",
]


def _etapa_exportar_pasta() -> None:
    print("\n=== ETAPA 5 — Exportando arquivos finais ===")
    hoje = date.today().strftime("%d-%m-%Y")
    pasta_saida = ROOT / "outputs" / hoje
    pasta_saida.mkdir(parents=True, exist_ok=True)

    for arquivo in _ARQUIVOS_SAIDA:
        if arquivo.exists():
            destino = pasta_saida / arquivo.name
            shutil.copy2(arquivo, destino)
            print(f"  ✅ {arquivo.name}")
        else:
            print(f"  ⚠️  Não encontrado: {arquivo.name}")

    print(f"\n  📁 Pasta gerada: {pasta_saida}")


# ---------------------------------------------------------------------------
# ETAPA 6 — Push automático para o GitHub
# ---------------------------------------------------------------------------

def _ler_env(chave: str) -> str:
    """Lê uma variável do arquivo .env sem depender de biblioteca externa."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    for linha in env_path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, _, v = linha.partition("=")
        if k.strip() == chave:
            return v.strip().strip('"').strip("'")
    return ""


def _git(args: list[str], env_extra: dict | None = None) -> tuple[bool, str]:
    env = None
    if env_extra:
        env = os.environ.copy()
        env.update(env_extra)
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=env,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return False, "git não encontrado — instale o Git ou ignore este passo."


_ARQUIVOS_COMMIT = [
    "base_pronta.csv",
    "base_falta_pronta.csv",
    "relatorionotas.csv",
    "relatorionotas_falta.csv",
    "tabela_justificativas_danos.csv",
    "tabela_justificativas_faltas.csv",
]


def _etapa_git_push() -> None:
    print("\n=== ETAPA 6 — Push automático para o GitHub ===")

    token = _ler_env("GITHUB_TOKEN")
    if not token:
        print("  ⚠️  GITHUB_TOKEN não encontrado no .env — pulando push automático.")
        print("  💡  Crie o arquivo .env na raiz com: GITHUB_TOKEN=seu_token_aqui")
        return

    # Verifica se o Git está instalado nesta máquina
    ok_git, _ = _git(["--version"])
    if not ok_git:
        print("  ⚠️  Git não está instalado nesta máquina — pulando push automático.")
        print("  💡  Instale o Git para Windows: https://git-scm.com/download/win")
        return

    # Garante identidade do Git (commit/merge exigem isso; em máquina nova pode não estar setado)
    _, nome_cfg = _git(["config", "user.name"])
    if not nome_cfg.strip():
        _git(["config", "user.name", "Pipeline Dias+"])
        _git(["config", "user.email", "pipeline@diasmais.local"])

    hoje = date.today().strftime("%d/%m/%Y")
    repo_url = f"https://{token}@github.com/icarocharleaux-mm/Dash-particionado.git"

    # git add
    for caminho in _ARQUIVOS_COMMIT:
        arq = ROOT / Path(caminho)
        if arq.exists():
            ok, _ = _git(["add", caminho])
            status = "✅" if ok else "⚠️ "
            print(f"  {status} git add {Path(caminho).name}")
        else:
            print(f"  —  Não encontrado: {caminho}")

    # git commit
    ok, out = _git(["commit", "-m", f"Atualiza bases finais — {hoje}"])
    _sem_mudanca = ("nothing to commit", "no changes added to commit")
    if not ok and any(m in out.lower() for m in _sem_mudanca):
        # Sem dados novos AGORA, mas pode existir commit local de execução anterior
        # que ainda não foi enviado — segue para sincronizar e empurrar mesmo assim.
        print("  ℹ️  Nada de novo para commitar; verificando commits pendentes para enviar...")
    elif not ok:
        print("  ❌ git commit")
        print(f"     {out}")
        return
    else:
        print("  ✅ git commit")

    # Sincroniza + push com retry. Como 3 máquinas usam o mesmo repositório, uma pode
    # empurrar quase ao mesmo tempo que a outra. A cada tentativa: pull (-X ours mantém
    # os CSVs recém-gerados) e push; se o push for rejeitado porque outra máquina empurrou
    # nesse meio-tempo, ressincroniza e tenta de novo (até 3 vezes).
    enviado = False
    for tentativa in range(1, 4):
        print(f"  ↻ Sincronizando com o GitHub (tentativa {tentativa}/3)...")
        ok, out = _git(["pull", "--no-rebase", "--no-edit", "-X", "ours", repo_url, "main"])
        if not ok:
            _git(["merge", "--abort"])   # desfaz merge pela metade, deixa o repo intacto
            print(f"     ⚠️  pull falhou: {out.replace(token, '***')}")
            continue
        ok, out = _git(["push", repo_url, "main"])
        if ok:
            enviado = True
            break
        print(f"     ↻ push rejeitado, ressincronizando: {out.replace(token, '***')}")

    if enviado:
        print("  ✅ Push realizado com sucesso!")
        print("  🌐 https://github.com/icarocharleaux-mm/Dash-particionado")
    else:
        print("  ❌ Não foi possível enviar após 3 tentativas.")
        print("     Rode manualmente: git pull --no-rebase -X ours origin main  e depois  git push origin main")


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------

def _pedir_periodo() -> tuple[str, str]:
    print("\n" + "=" * 60)
    print("FILTRO DE PERÍODO — OFENSORES")
    print("=" * 60)
    inicio = input("Data inicial (ex: 01/04/2026) [ENTER = histórico todo]: ").strip()
    fim = ""
    if inicio:
        fim = input("Data final   (ex: 30/04/2026) [ENTER = hoje]:          ").strip()
    return inicio, fim


async def _main() -> None:
    print("=" * 60)
    print("PIPELINE DIAS+ — BASE NATURA → DIASLOG → DASHBOARD")
    print("=" * 60)

    headless = input("\nRodar browser em modo invisível? (s/N): ").strip().lower() == "s"
    data_inicio, data_fim = _pedir_periodo()

    _etapa_converter_bases()
    await _etapa_relatorios(headless=headless)
    _etapa_limpeza_faltas()
    _etapa_limpeza_danos(data_inicio, data_fim)
    _etapa_gerar_excel_tratativas()
    _etapa_exportar_pasta()
    _etapa_git_push()

    print("\n" + "=" * 60)
    print("✅ Pipeline concluído!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_main())
