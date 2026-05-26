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
    src = BASE2 / "base_falta_pronta.csv"
    dst = ROOT / "base_falta_pronta.csv"
    if src.exists():
        shutil.copy2(src, dst)
        print(f"  ✅ Copiado para raiz: {dst.name}")


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
# ETAPA 4 — Git commit e push
# ---------------------------------------------------------------------------

def _etapa_git_push() -> None:
    print("\n=== ETAPA 4 — Git Commit & Push ===")
    hoje = date.today().strftime("%d/%m/%Y")
    for cmd in [
        ["git", "add", "-A"],
        ["git", "commit", "-m", f"Atualização dados {hoje}"],
        ["git", "push"],
    ]:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  ⚠️  {' '.join(cmd)}: {r.stderr.strip()}")
        else:
            print(f"  ✅ {' '.join(cmd)}")


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
    _etapa_git_push()

    print("\n" + "=" * 60)
    print("✅ Pipeline concluído!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_main())
