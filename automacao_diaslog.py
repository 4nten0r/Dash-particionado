"""
Playwright: login no Diaslog, preenche o formulário de consulta por lote e baixa o relatório.

Pré-requisitos (rodar uma vez):
    pip install playwright python-dotenv openpyxl
    playwright install chromium
"""
import asyncio
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

_BASE_URL = "https://sistema.diaslog.com.br"
_LOGIN_URL = f"{_BASE_URL}/Login"
_CONSULTA_URL = f"{_BASE_URL}/restrito/Consulta_NotafiscalLote.aspx"


async def baixar_relatorio_notas(pedidos: list[str], destino: str, headless: bool = False) -> None:
    """
    Acessa o sistema Diaslog, cola os pedidos no formulário e salva o relatório em `destino`.

    headless=False abre o browser visível (recomendado na primeira execução para validar).
    headless=True roda silencioso em produção.
    """
    usuario = os.getenv("DIASLOG_USUARIO")
    senha = os.getenv("DIASLOG_SENHA")
    if not usuario or not senha:
        raise RuntimeError(
            "Credenciais não encontradas. Crie o arquivo .env com:\n"
            "  DIASLOG_USUARIO=seu_usuario\n"
            "  DIASLOG_SENHA=sua_senha"
        )

    pedidos_unicos = sorted({str(p).strip() for p in pedidos if str(p).strip()})
    print(f"  [Diaslog] {len(pedidos_unicos)} pedidos | destino: {destino}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # --- Login ---
            print("  [Diaslog] Fazendo login...")
            await page.goto(_LOGIN_URL, wait_until="networkidle")
            await page.locator('#txtusername').fill(usuario)
            await page.locator('#txtpass').fill(senha)
            # Botão de login é um <a> com postback, não um input[submit]
            await page.locator('#lnkLogin').click()
            await page.wait_for_url("**/restrito/**", timeout=20_000)
            print("  [Diaslog] Login OK.")

            # --- Formulário de consulta ---
            await page.goto(_CONSULTA_URL, wait_until="networkidle")

            # Tipo de filtro → Pedido
            await page.locator('#MainContent_cmbTipo').select_option(label='Pedido')

            # Data início de embarque (data mínima — pega tudo desde o início de 2025)
            await page.locator('#MainContent_txtDT_IniEmbarque').fill('01/01/2025')
            # Data fim: deixa em branco para pegar até hoje

            # Checkboxes conforme configuração padrão do usuário:
            #   chkAtivo     = Ocorrências informativas
            #   chkUltima    = Apenas a última ocorrência
            #   chkUltimaEDI = Apenas a última ocorrência Finalizadora (EDI)
            await page.locator('#MainContent_chkAtivo').check()
            await page.locator('#MainContent_chkUltima').check()
            await page.locator('#MainContent_chkUltimaEDI').check()

            # Formato de saída → Excel (para download automático)
            await page.locator('#MainContent_ddlTipoRelatorio').select_option(label='Exportar para Excel')

            # Cola os pedidos via JavaScript (evita timeout do fill() com listas grandes)
            texto = '\n'.join(pedidos_unicos)
            await page.locator('#MainContent_txtnotas').evaluate(
                f'(el) => {{ el.value = {__import__("json").dumps(texto)}; }}'
            )

            # Gerar relatório e capturar o download
            print("  [Diaslog] Aguardando geração do relatório (pode demorar)...")
            async with page.expect_download(timeout=300_000) as dl_info:
                await page.locator('#MainContent_btnGerarRelatorio').click()

            download = await dl_info.value
            nome = download.suggested_filename
            print(f"  [Diaslog] Baixado: {nome}")

            destino_path = Path(destino)
            destino_path.parent.mkdir(parents=True, exist_ok=True)

            # Converte Excel → CSV preservando todas as linhas (incluindo as 7 de cabeçalho)
            tmp = Path("_tmp_dl") / nome
            tmp.parent.mkdir(exist_ok=True)
            await download.save_as(str(tmp))
            _excel_para_csv(str(tmp), str(destino_path))
            shutil.rmtree("_tmp_dl", ignore_errors=True)

            print(f"  ✅ Relatório salvo: {destino_path}")

        finally:
            await browser.close()


def _excel_para_csv(origem: str, destino: str) -> None:
    """Converte Excel para CSV com separador ; preservando todas as linhas."""
    import pandas as pd
    # header=None para não pular nenhuma linha (limpeza.py usa skiprows=7)
    df = pd.read_excel(origem, header=None)
    df.to_csv(destino, sep=';', index=False, encoding='utf-8-sig', header=False)
    print(f"  [Diaslog] Excel convertido para CSV ({len(df)} linhas): {destino}")


# Teste manual: python automacao_diaslog.py
if __name__ == "__main__":
    asyncio.run(
        baixar_relatorio_notas(
            pedidos=["123456", "789012"],
            destino="teste_relatorio.csv",
            headless=False,
        )
    )
