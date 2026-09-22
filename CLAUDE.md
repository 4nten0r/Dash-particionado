# CLAUDE.md — Painel Logístico Dias+ (Danos & Faltas Natura)

Contexto para o Claude entender o projeto sem redescobrir tudo a cada sessão.
Idioma: **PT-BR, direto**.

## O que é
Painel Streamlit que analisa **Danos** e **Faltas** de mercadorias da **Natura**, operados pela transportadora **Dias+**. Cruza a base da Natura com o relatório de notas do sistema **Diaslog**.

- **Dashboard online:** https://basenatura.streamlit.app
- **Repositório:** https://github.com/4nten0r/dash-particionado
- **Branch principal:** `main`

## Arquitetura (arquivos)
| Arquivo | Papel |
|---|---|
| `app.py` | App Streamlit principal (abas/menu, KPIs, gráficos, PDF). |
| `dados.py` | `load_data()` — **cacheado** (`@st.cache_data ttl=300`). Lê os CSVs, monta `df_danos`, `df_faltas`, `df_unificado`, mapas geográficos e enriquecimentos. |
| `graficos.py` | Funções de gráfico Plotly (curva ABC, heatmap recorrência, mapa de rotas, evolução temporal, comparativo). |
| `filtros.py` | Sidebar de filtros (filial, motorista, empresa, canal, categoria, período, outliers). |
| `main.py` | **Pipeline** completo (ETAPAS 0–6). Roda com `python main.py`. |
| `limpeza.py` | Gera `base_pronta.csv` (Danos) + `tabela_justificativas_danos/faltas.csv`. |
| `BASE2/limpeza_falta.py` | Gera `base_falta_pronta.csv` (Faltas). |
| `automacao_diaslog.py` | Baixa relatórios do Diaslog (Playwright). Expõe `_fazer_login()` (compartilhado) e `testar_login()` (usado pelo botão de teste do painel). |
| `credenciais_seguras.py` | Salva/carrega usuário e senha do Diaslog **criptografados via Windows DPAPI**, vinculados ao usuário/máquina. Usado pelo painel gráfico; opcional (fallback é o `.env`). |
| `upload_github.py` | Botão manual de push (servidor HTTP local, uso avulso). |
| `painel_execucao.pyw` | **Painel gráfico (Tkinter)** para rodar o pipeline sem terminal — ver seção própria abaixo. |
| `Abrir Painel Dias+.bat` | Duplo clique → abre o `painel_execucao.pyw` sem console. |
| `gerar_painel_filiais.py` | Gera relatório semanal impresso (HTML) por filial, sem dado de motorista/cliente. |

## Fluxo do pipeline (`main.py`)
0. Detecta e converte os Excel da Natura → `base.csv` / `BASE2/base_falta.csv`.
1. Extrai pedidos filtrados por transportadora Dias.
2. Baixa relatórios do Diaslog → `relatorionotas.csv` / `BASE2/relatorionotas_falta.csv`.
3. `limpeza_falta.py` → `base_falta_pronta.csv` (copiado para a raiz).
4. `limpeza.py` → `base_pronta.csv` + tabelas de justificativas.
5. Gera `outputs/<data>/tratativas.xlsx` (+ OneDrive) e exporta os finais.
6. **Push automático** para o GitHub (usa `GITHUB_TOKEN` do `.env`).

## Dados e cruzamentos (importante)
- **Chave de cruzamento confiável = `Pedido`** (100% de match). A `Rota` tem codificação divergente entre Natura e Diaslog — não usar para cruzar ocorrências.
- Danos cruza com `relatorionotas.csv`; Faltas com `relatorionotas_falta.csv` (**cruzar com o arquivo errado dá ~1% de match**).
- O `relatorionotas` tem ~65 colunas; o painel usa poucas. Colunas ricas já aproveitadas/aproveitáveis por Pedido: `Efetividade`/`Offset` (SLA), `Valor Mercadoria`/`Valor Frete`, `Ocorrência`/`Obs Ocorrência` (causa), `Código do Destinatário` (código do cliente), `Cidade`/`Bairro`/`LAT`/`LON`.
- **`cod_cliente` só existe na base de Danos.** Para código de cliente em Faltas, puxar `Código do Destinatário` do `relatorionotas` por Pedido.
- **Filiais unificadas** em `dados.py`: `DIAS MD MEGA RIO DE JANEIRO`, `DIAS DCX BAIXADA FLUMINENSE`, `DIAS DUQUE DE CAXIAS MEGA FILIAL` → `DIAS DUQUE DE CAXIAS`.
- **`CD_Origem`** (centro de distribuição da Natura/Avon que despachou a carga): Danos usa `centro_distribuicao` (já selecionada por nome em `limpeza.py`); Faltas usa `distribution_center_name` (coluna Q/índice 16 em `base_falta.csv`, adicionada em `BASE2/limpeza_falta.py`). Normalizado em `dados.py` (`_normalizar_cd_origem`) porque a grafia diverge entre as duas bases: `CD SÃO PAULO`/`NASP`, `CD MATIAS BARBOSA`/`MATIAS BARBOSA`, `CD CABREÚVA`/`CABREUVA` → mesmos 3 nomes canônicos. Filtrando só a nossa transportadora, preenchimento é 100% dos dois lados.
- **`base_pronta.csv`/`base_falta_pronta.csv` devem ser lidos com `encoding="utf-8-sig"`** em `dados.py` (não `latin-1`) — é assim que `limpeza.py`/`limpeza_falta.py` os escrevem; ler com o encoding errado corrompe acentos (ex.: "CABREÚVA" virava "CABREÃVA"). `relatorionotas*.csv` (fonte externa, Diaslog) continuam em `latin-1` — não mexer nesses.

## Convenções técnicas (gotchas que já morderam)
- **Datas brasileiras:** sempre `pd.to_datetime(..., dayfirst=True, format='mixed', errors='coerce')`. Sem `dayfirst`, dias > 12 viram `NaT` e somem.
- **Encoding:** CSVs em `latin-1`, separador `;`. Limpar BOM/`ï»¿` e dar `strip().lower()` nos cabeçalhos.
- **Ano nos meses:** para séries temporais usar **Ano-Mês** (`Data_Filtro.dt.to_period('M')`), nunca só `Periodo` (nome do mês sem ano) — senão mistura Set/2025 com Set/2026.
- **Seleção de colunas por NOME, não por posição** — o layout dos Excel da Natura muda de ordem (`Base_R` vs `Base_Reclamação`).
- **`base_pronta.csv` pode não estar na raiz** (às vezes só em `outputs/<data>/`). Se sumir, `df_danos` fica vazio.
- **Versões travadas** no `requirements.txt` (`pandas<3.0`, `streamlit<1.58`) — pandas 3.x quebra o parsing de datas no Streamlit Cloud.

## Painel de Execução (interface gráfica do pipeline)
- `python main.py` continua funcionando normalmente no terminal (modo interativo, com os prompts de sempre).
- Para quem prefere não usar terminal: `painel_execucao.pyw` é uma GUI Tkinter (sem dependência nova) com checkbox de modo headless, campos de data e log ao vivo. Abre via duplo clique em `Abrir Painel Dias+.bat` (ou no atalho "Painel Dias+" da Área de Trabalho, quando existir — é local a cada máquina, não versionado).
- Por baixo, o painel chama `python main.py --auto [--headless] [--data-inicio dd/mm/aaaa] [--data-fim dd/mm/aaaa]` — a flag `--auto` pula os `input()` interativos. Qualquer alteração nos prompts de `_main()`/`_pedir_periodo()` deve manter os dois caminhos (interativo e `--auto`) em sincronia.
- O `.bat` usa `%~dp0` (caminho relativo a si mesmo) — funciona em qualquer máquina que clonar o repo, sem editar nada.
- **Credenciais do Diaslog no painel:** campo opcional de usuário/senha com botões Salvar/Testar/Remover. Salva **criptografado via DPAPI** (`credenciais_seguras.py`) em `BASE2/.diaslog_cred.enc` — só decifrável pelo mesmo usuário/máquina do Windows (nunca versionado; está no `.gitignore`). Se preenchido, tem prioridade sobre o `.env` só para aquela execução (injetado via variável de ambiente no processo filho, nunca escrito em disco em texto puro); se vazio, comportamento de sempre (lê o `.env`). **Acesso ao TMS via automação precisa ser informado ao Marcelo e Isabella** (regra da organização).

## Deploy (Streamlit Cloud)
- Push no GitHub → o app atualiza sozinho, **mas o cache do `load_data()` persiste**.
- **Mudou `dados.py` (lógica/assinatura/cache) → precisa "Reboot app"** no Streamlit Cloud (Manage app → ⋮ → Reboot app). Mudança só de layout em `app.py` geralmente não precisa.

## Git / multi-máquina
- O pipeline roda em **3 máquinas** com o **mesmo `.env`**; todas dão push no mesmo repo.
- **Código** (`app.py`, `dados.py`, etc.) deve ser alterado **numa única máquina de dev** (com o Claude). As outras só rodam o pipeline (dados) e puxam o resto.
- A ETAPA 6 do `main.py` faz **pull antes do push com retry** (`-X ours` mantém os CSVs recém-gerados) e configura identidade do git — não precisa mexer no git na mão.
- Máquina nova precisa: **Git instalado**, ser um **clone** do repo (não cópia solta), `.env` com token.
- **Não** colocar a pasta (com `.git`) dentro de pasta sincronizada por OneDrive (corrompe).
- Quem roda o pipeline **por último sobrescreve** os CSVs no GitHub (`-X ours`).

## LGPD (regra da organização)
Ao criar **material** (planilha, HTML, dashboard, exportação): remover CPF, RG, CNH, endereço residencial, telefone, e-mail pessoal, dados bancários PF. Usar filial, OS, SLA, CNPJ PJ e métricas agregadas; mascarar quando necessário. Clientes Natura são majoritariamente **consultoras (PF)** — cuidado com nome + código em materiais compartilhados. **Nunca** usar CPF/CNPJ do `relatorionotas` em saídas.

## Como trabalhar comigo (Claude)
- Antes de features grandes: descrever o **objetivo**; eu proponho o plano antes de codar.
- Mudanças de código só nesta máquina de dev.
- Colar **texto** do erro (melhor que print; não expõe o token).
- Arquivos novos vão em `outputs/`; não renomear/mover/excluir sem avisar.
