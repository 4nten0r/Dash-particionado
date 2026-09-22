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
import argparse
import asyncio
import csv
import glob
import os
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo


import pandas as pd
from openpyxl import load_workbook

from automacao_diaslog import baixar_relatorio_notas

ROOT = Path(__file__).parent
BASE2 = ROOT / "BASE2"


def _configurar_saida_terminal() -> None:
    """Mantém acentos e símbolos do log legíveis no console do Windows."""
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8", errors="replace")

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


def _normalizar_transportadora(valor: object) -> str:
    return "".join(str(valor).upper().split()).replace(".", "")


_TRANSPORTADORAS_FALTAS_NORMALIZADAS = {
    _normalizar_transportadora(nome) for nome in _TRANSPORTADORAS_FALTAS
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


# Colunas que identificam UNICAMENTE uma falta (para remover repetidas entre arquivos)
_COLS_FALTA_DEDUP = [
    "data_hr_faturamento", "nm_pedido", "marca_canal", "nome_transportadora",
    "rota", "filial", "name1", "nat_productsellcode", "categoria",
    "product_description", "description", "cantidad_itens",
]


# Pasta dedicada com os PPM Falta OFICIAIS (um por trimestre, sob controle do usuário).
# Evita pegar as dezenas de downloads repetidos que se acumulam no Downloads.
_FALTAS_FONTE = BASE2 / "faltas_fonte"


def _arquivos_falta() -> list[Path]:
    """Arquivos PPM Falta a consolidar. Preferência: pasta dedicada BASE2/faltas_fonte/.
    Se ela não existir/estiver vazia, cai no comportamento antigo (o PPM Falta mais
    recente do Downloads/Desktop/Documentos)."""
    if _FALTAS_FONTE.is_dir():
        achados = [p for p in _FALTAS_FONTE.glob("*.xlsx") if not p.name.startswith("~$")]
        if achados:
            return sorted(achados, key=os.path.getmtime)
        print(f"  ⚠️  {_FALTAS_FONTE} está vazia — usando o PPM Falta mais recente do Downloads.")
    return [_encontrar_excel("PPM Falta*.xlsx")]


def _validar_arquivo_excel(caminho: Path, descricao: str) -> Path:
    caminho = Path(caminho).expanduser()
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo de {descricao} não encontrado: {caminho}")
    if caminho.suffix.lower() not in (".xlsx", ".xlsm"):
        raise ValueError(f"Arquivo de {descricao} precisa ser Excel (.xlsx ou .xlsm): {caminho}")
    return caminho.resolve()


def _arquivos_falta_informados(valor: str) -> list[Path]:
    """Converte caminhos digitados no terminal em arquivos PPM Falta."""
    caminhos = [Path(item.strip().strip('"')) for item in valor.split(";") if item.strip()]
    arquivos = []
    for caminho in caminhos:
        if caminho.is_dir():
            arquivos.extend(sorted(caminho.glob("*.xlsx")))
            arquivos.extend(sorted(caminho.glob("*.xlsm")))
        else:
            arquivos.append(caminho)
    if not arquivos:
        raise FileNotFoundError("Nenhum arquivo Excel de Faltas foi encontrado no caminho informado.")
    return [_validar_arquivo_excel(caminho, "Faltas") for caminho in arquivos]


def _xlsx_para_csv_stream(origem: Path, destino: Path) -> int:
    """Excel → CSV em streaming (openpyxl read_only) — rápido e leve p/ arquivos grandes."""
    wb = load_workbook(str(origem), read_only=True)
    ws = wb.active
    destino.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        for row in ws.iter_rows(values_only=True):
            w.writerow(["" if v is None else v for v in row])
            n += 1
    wb.close()
    return n


def _etapa_converter_bases(
    excel_danos: Path | None = None,
    arquivos_falta: list[Path] | None = None,
) -> None:
    print("\n=== ETAPA 0 — Conversão dos Excel da Natura ===")

    excel_danos = _validar_arquivo_excel(
        excel_danos or _encontrar_excel("Reclamações*.xlsx"), "Danos"
    )
    _excel_para_csv_base(excel_danos, ROOT / "base.csv")

    # Faltas: a Natura manda vários PPM (trimestres) com períodos SOBREPOSTOS e rótulos
    # trocados. Consolidamos os arquivos oficiais (pasta faltas_fonte) e removemos as
    # faltas repetidas pela identidade da ocorrência, para não contar em dobro no dashboard.
    arquivos_falta = arquivos_falta or _arquivos_falta()
    arquivos_falta = [_validar_arquivo_excel(arquivo, "Faltas") for arquivo in arquivos_falta]
    tmp_dir = BASE2 / "_tmp_falta"
    dfs = []
    for i, arq in enumerate(arquivos_falta):
        print(f"  → Convertendo (falta): {arq.name}")
        tmp = tmp_dir / f"f{i}.csv"
        _xlsx_para_csv_stream(arq, tmp)
        dfs.append(pd.read_csv(tmp, sep=";", encoding="utf-8-sig", dtype=str, low_memory=False))
    base_falta = pd.concat(dfs, ignore_index=True)
    antes = len(base_falta)
    chave = [c for c in _COLS_FALTA_DEDUP if c in base_falta.columns]
    if chave:
        base_falta = base_falta.drop_duplicates(subset=chave, keep="first")
    base_falta.to_csv(BASE2 / "base_falta.csv", sep=";", index=False, encoding="utf-8-sig")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"  ✅ Faltas consolidadas: {len(base_falta)} linhas "
          f"({antes - len(base_falta)} repetidas removidas de {len(arquivos_falta)} arquivo(s))")


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


def _ler_colunas(caminho: Path, colunas: list[str]) -> pd.DataFrame:
    """Lê SOMENTE as colunas indicadas — leve em memória para bases grandes
    (a base.csv da Natura tem ~95 colunas e >190 MB; carregá-la inteira pode
    estourar a RAM durante o pipeline). Fallback para a leitura completa."""
    for enc in ("utf-8", "latin1"):
        try:
            return pd.read_csv(caminho, sep=";", encoding=enc, usecols=colunas, dtype=str)
        except ValueError:
            break  # coluna não existe com este separador → cai no fallback
        except Exception:
            continue
    df = _ler_csv(caminho)
    return df[[c for c in colunas if c in df.columns]]


def _limpar_pedido(serie: pd.Series) -> list[str]:
    serie = serie.dropna().astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    return [p for p in serie.unique() if p and p.upper() not in ("NAN", "NONE", "")]


def _extrair_pedidos_danos() -> list[str]:
    df = _ler_colunas(ROOT / "base.csv", ["transportadora", "pedido"])
    df = df[df["transportadora"].astype(str).str.contains("DIAS", case=False, na=False)]
    pedidos = _limpar_pedido(df["pedido"])
    print(f"  → {len(pedidos)} pedidos Dias únicos (danos)")
    return pedidos


def _extrair_pedidos_faltas() -> list[str]:
    df = _ler_colunas(BASE2 / "base_falta.csv", ["nome_transportadora", "nm_pedido"])
    transportadoras = df["nome_transportadora"].map(_normalizar_transportadora)
    df = df[transportadoras.isin(_TRANSPORTADORAS_FALTAS_NORMALIZADAS)]
    pedidos = _limpar_pedido(df["nm_pedido"])
    print(f"  → {len(pedidos)} pedidos Dias únicos (faltas)")
    return pedidos


# ---------------------------------------------------------------------------
# ETAPA 1 — Baixar relatórios no Diaslog
# ---------------------------------------------------------------------------

# O sistema Dias falha ao gerar relatórios muito grandes; baixamos em lotes deste tamanho.
_MAX_PEDIDOS_LOTE = 6000


async def _baixar_em_lotes(pedidos: list[str], destino: Path, headless: bool) -> None:
    """Baixa o relatório do Diaslog em lotes (evita o travamento com muitos pedidos)
    e junta tudo num único CSV. Preserva as 7 linhas de cabeçalho apenas do 1º lote.
    A junção é feita com pandas (respeita campos de texto com quebra de linha)."""
    destino = Path(destino)
    total = len(pedidos)
    if total <= _MAX_PEDIDOS_LOTE:
        await baixar_relatorio_notas(pedidos=pedidos, destino=str(destino), headless=headless)
        return

    n_partes = (total + _MAX_PEDIDOS_LOTE - 1) // _MAX_PEDIDOS_LOTE
    print(f"  [Diaslog] {total} pedidos → dividindo em {n_partes} partes "
          f"(limite {_MAX_PEDIDOS_LOTE}/parte)")
    temps = []
    for i in range(n_partes):
        lote = pedidos[i * _MAX_PEDIDOS_LOTE:(i + 1) * _MAX_PEDIDOS_LOTE]
        tmp = destino.with_name(f"{destino.stem}_parte{i + 1}{destino.suffix}")
        print(f"\n  [Diaslog] === Parte {i + 1}/{n_partes} ({len(lote)} pedidos) ===")
        await baixar_relatorio_notas(pedidos=lote, destino=str(tmp), headless=headless)
        temps.append(tmp)

    # Junta: parte 1 inteira (7 preâmbulo + cabeçalho + dados); demais só os dados (pula 8 linhas)
    dfs = []
    for i, tmp in enumerate(temps):
        skip = 0 if i == 0 else 8
        dfs.append(pd.read_csv(tmp, sep=";", header=None, skiprows=skip, dtype=str,
                               encoding="utf-8-sig", keep_default_na=False, low_memory=False))
    combinado = pd.concat(dfs, ignore_index=True)
    combinado.to_csv(destino, sep=";", header=False, index=False, encoding="utf-8-sig")
    for tmp in temps:
        tmp.unlink(missing_ok=True)
    print(f"\n  ✅ Relatório consolidado ({n_partes} partes → {len(combinado)} linhas): {destino}")


async def _etapa_relatorios(headless: bool) -> None:
    print("\n=== ETAPA 1 — Relatórios Diaslog ===")

    print("\n[Danos]")
    pedidos_danos = _extrair_pedidos_danos()
    if not pedidos_danos:
        raise RuntimeError("Nenhum pedido de Danos da transportadora Dias foi encontrado.")
    await _baixar_em_lotes(
        pedidos=pedidos_danos,
        destino=ROOT / "relatorionotas.csv",
        headless=headless,
    )

    print("\n[Faltas]")
    pedidos_faltas = _extrair_pedidos_faltas()
    if not pedidos_faltas:
        raise RuntimeError("Nenhum pedido de Faltas da transportadora Dias foi encontrado.")
    await _baixar_em_lotes(
        pedidos=pedidos_faltas,
        destino=BASE2 / "relatorionotas_falta.csv",
        headless=headless,
    )


# ---------------------------------------------------------------------------
# ETAPA 2 — Limpeza faltas
# ---------------------------------------------------------------------------

def _etapa_limpeza_faltas() -> None:
    print("\n=== ETAPA 2 — Limpeza Faltas ===")
    inicio = time.time()
    subprocess.run([sys.executable, "limpeza_falta.py"], cwd=str(BASE2), check=True)
    saida = BASE2 / "base_falta_pronta.csv"
    if not saida.exists() or saida.stat().st_mtime < inicio:
        raise RuntimeError("A limpeza de Faltas não gerou uma base nova.")
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
    inicio = time.time()
    subprocess.run(
        [sys.executable, "limpeza.py"],
        cwd=str(ROOT),
        input=f"{data_inicio}\n{data_fim}\n",
        text=True,
        check=True,
    )
    saidas = (ROOT / "base_pronta.csv", ROOT / "tabela_justificativas_danos.csv")
    ausentes = [str(saida.name) for saida in saidas if not saida.exists() or saida.stat().st_mtime < inicio]
    if ausentes:
        raise RuntimeError("A limpeza de Danos não gerou arquivos novos: " + ", ".join(ausentes))


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
    """Lê uma variável do arquivo de ambiente na raiz do projeto."""
    env_path = next((p for p in (ROOT / "env", ROOT / ".env") if p.exists()), None)
    if env_path is None:
        return ""
    for linha in env_path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, _, v = linha.partition("=")
        if k.strip() == chave:
            return v.strip().strip('"').strip("'")
    return ""


_GIT_EXE: str | None = None  # cache — evita reprocurar a cada chamada


def _localizar_git() -> str:
    """Encontra o executável do git de forma robusta.

    `subprocess.run(["git"])` depende do PATH do processo em execução. Quando o
    pipeline é lançado pelo Painel de Execução (duplo clique → Explorer → pyw.exe),
    o processo herda o ambiente do Explorer, que só reflete alterações de PATH após
    logoff/logon — mesmo com o Git instalado, o comando pode não ser encontrado
    (já aconteceu em produção). Por isso: tenta o PATH primeiro e, se falhar, procura
    nos locais de instalação padrão do Git para Windows.
    """
    global _GIT_EXE
    if _GIT_EXE:
        return _GIT_EXE

    candidatos = [shutil.which("git")]
    candidatos += [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "cmd" / "git.exe"),
    ]
    for candidato in candidatos:
        if candidato and Path(candidato).exists():
            _GIT_EXE = candidato
            return _GIT_EXE

    _GIT_EXE = "git"  # nenhum encontrado; mantém o nome simples para a mensagem de erro
    return _GIT_EXE


def _git(args: list[str], env_extra: dict | None = None) -> tuple[bool, str]:
    env = None
    if env_extra:
        env = os.environ.copy()
        env.update(env_extra)
    try:
        result = subprocess.run(
            [_localizar_git()] + args,
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
    "data_atualizacao.txt",
]

_GITHUB_REPOSITORIO_PADRAO = "4nten0r/dash-particionado"


def _etapa_git_push() -> bool:
    print("\n=== ETAPA 6 — Push automático para o GitHub ===")

    token = _ler_env("GITHUB_TOKEN")
    if not token:
        print("  ❌ GITHUB_TOKEN não encontrado no arquivo env — push não realizado.")
        print("  💡  Crie o arquivo env na raiz com: GITHUB_TOKEN=seu_token_aqui")
        return False

    # Verifica se o Git está instalado nesta máquina
    ok_git, _ = _git(["--version"])
    if not ok_git:
        print("  ❌ Git não está instalado nesta máquina — push não realizado.")
        print("  💡  Instale o Git para Windows: https://git-scm.com/download/win")
        return False

    # A pasta pode ter sido copiada sem o diretório oculto .git.
    if not (ROOT / ".git").exists():
        ok, out = _git(["init", "-b", "main"])
        if not ok:
            ok, out = _git(["init"])
            if ok:
                _git(["branch", "-M", "main"])
        if not ok:
            print("  ❌ Não foi possível inicializar o repositório Git.")
            print(f"     {out}")
            return False
        print("  ✅ Repositório Git inicializado na pasta do projeto.")

    # Garante identidade do Git (commit/merge exigem isso; em máquina nova pode não estar setado)
    _, nome_cfg = _git(["config", "user.name"])
    if not nome_cfg.strip():
        nome = _ler_env("GIT_USER_NAME") or "Antenor"
        email = _ler_env("GIT_USER_EMAIL") or ""
        _git(["config", "user.name", nome])
        if email:
            _git(["config", "user.email", email])

    hoje = date.today().strftime("%d/%m/%Y")
    (ROOT / "data_atualizacao.txt").write_text(
        f"{hoje} às {pd.Timestamp.now(tz=ZoneInfo('America/Sao_Paulo')).strftime('%H:%M')}\n",
        encoding="utf-8",
    )
    repositorio = _ler_env("GITHUB_REPOSITORY") or _GITHUB_REPOSITORIO_PADRAO
    repositorio = repositorio.removeprefix("https://github.com/").removesuffix(".git").strip("/")
    repo_url = f"https://{token}@github.com/{repositorio}.git"

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
        return False
    else:
        print("  ✅ git commit")

    # Sincroniza + push com retry. Como 3 máquinas usam o mesmo repositório, uma pode
    # empurrar quase ao mesmo tempo que a outra. A cada tentativa: pull (-X ours mantém
    # os CSVs recém-gerados) e push; se o push for rejeitado porque outra máquina empurrou
    # nesse meio-tempo, ressincroniza e tenta de novo (até 3 vezes).
    enviado = False
    for tentativa in range(1, 4):
        print(f"  ↻ Sincronizando com o GitHub (tentativa {tentativa}/3)...")
        ok, out = _git([
            "pull", "--no-rebase", "--no-edit", "--allow-unrelated-histories",
            "-X", "ours", repo_url, "main",
        ])
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
        print(f"  🌐 https://github.com/{repositorio}")
    else:
        print("  ❌ Não foi possível enviar após 3 tentativas.")
        print("     Rode manualmente: git pull --no-rebase -X ours origin main  e depois  git push origin main")
    return enviado


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


def _pedir_arquivos_bases() -> tuple[Path, list[Path]]:
    print("\n" + "=" * 60)
    print("ARQUIVOS DE ENTRADA — DANOS E FALTAS")
    print("=" * 60)
    print("ENTER em Danos usa o Excel 'Reclamações*.xlsx' mais recente.")
    danos = input("Caminho do Excel de Danos [ENTER = automático]: ").strip()
    excel_danos = _validar_arquivo_excel(
        Path(danos) if danos else _encontrar_excel("Reclamações*.xlsx"), "Danos"
    )

    print("\nEm Faltas, informe um ou mais arquivos separados por ';' ou uma pasta.")
    print(f"ENTER usa a pasta padrão: {_FALTAS_FONTE}")
    faltas = input("Caminho(s) do(s) Excel de Faltas [ENTER = automático]: ").strip()
    arquivos_falta = _arquivos_falta_informados(faltas) if faltas else _arquivos_falta()
    return excel_danos, arquivos_falta


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pipeline Dias+ — Base Natura → Diaslog → Dashboard")
    p.add_argument("--auto", action="store_true",
                   help="Pula as perguntas interativas (usado pelo Painel de Execução). "
                        "Use junto com --headless / --data-inicio / --data-fim.")
    p.add_argument("--headless", action="store_true",
                   help="Roda o navegador em modo invisível (sem --auto, ainda é perguntado no terminal).")
    p.add_argument("--data-inicio", default="", help="Data inicial do filtro de ofensores (dd/mm/aaaa).")
    p.add_argument("--data-fim", default="", help="Data final do filtro de ofensores (dd/mm/aaaa).")
    p.add_argument("--arquivo-danos", default="", help="Caminho do Excel de Danos.")
    p.add_argument("--arquivo-falta", action="append", default=[],
                   help="Caminho de um Excel/pasta de Faltas; pode repetir a opção.")
    return p.parse_args()


async def _main() -> None:
    print("=" * 60)
    print("PIPELINE DIAS+ — BASE NATURA → DIASLOG → DASHBOARD")
    print("=" * 60)

    args = _parse_args()
    if args.auto:
        # Chamado pelo Painel de Execução (painel_execucao.pyw) — sem prompts interativos.
        headless = args.headless
        data_inicio, data_fim = args.data_inicio, args.data_fim
        excel_danos = _validar_arquivo_excel(
            Path(args.arquivo_danos) if args.arquivo_danos else _encontrar_excel("Reclamações*.xlsx"),
            "Danos",
        )
        if args.arquivo_falta:
            arquivos_falta = _arquivos_falta_informados(";".join(args.arquivo_falta))
        else:
            arquivos_falta = _arquivos_falta()
        print(f"\n[Painel] Modo automático — headless={headless}, "
              f"período={data_inicio or 'histórico todo'} a {data_fim or '(hoje)'}")
    else:
        headless = input("\nRodar browser em modo invisível? (s/N): ").strip().lower() == "s"
        excel_danos, arquivos_falta = _pedir_arquivos_bases()
        data_inicio, data_fim = _pedir_periodo()

    _etapa_converter_bases(excel_danos, arquivos_falta)
    await _etapa_relatorios(headless=headless)
    _etapa_limpeza_faltas()
    _etapa_limpeza_danos(data_inicio, data_fim)
    _etapa_gerar_excel_tratativas()
    _etapa_exportar_pasta()
    if not _etapa_git_push():
        raise RuntimeError("O pipeline terminou sem realizar o commit/push no GitHub.")

    print("\n" + "=" * 60)
    print("✅ Pipeline concluído!")
    print("=" * 60)


if __name__ == "__main__":
    _configurar_saida_terminal()
    asyncio.run(_main())
