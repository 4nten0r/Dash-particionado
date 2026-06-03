import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import traceback
import requests
from fpdf import FPDF
from io import BytesIO
import streamlit.components.v1 as components
import json
import os
from streamlit_option_menu import option_menu

# --- IMPORTANDO AS BIBLIOTECAS DE AUTENTICAÇÃO ---
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# --- IMPORTANDO AS CAMADAS ---
from dados import load_data
from filtros import aplicar_filtros_barra_lateral
from graficos import (plot_top_motoristas, plot_comparativo_filial, plot_pizza_tipo_ocorrencia, 
                      plot_curva_abc, plot_heatmap_recorrencia, plot_mapa_rotas,
                      plot_evolucao_temporal, plot_comparativo_temporal_tipo)

# Configuração da Página e CSS (DEVE SER O PRIMEIRO COMANDO)
st.set_page_config(page_title="Dias+ Painel Logístico", layout="wide", page_icon="🚀")

# ==========================================
# INJEÇÃO DA IDENTIDADE VISUAL DIAS+ (CSS)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap');

    :root {
      --t1: #2DC5B4;
      --t2: #1A8090;
      --t3: #1A5A68;
      --t4: #5BA8B8;
      --bg: #0B2E3A;
      --red: #C47A77;
      --amber: #eab308;
      --w:  rgba(255,255,255,1);
      --w8: rgba(255,255,255,.8);
      --w5: rgba(255,255,255,.5);
    }

    /* Aplicação Global da Fonte e Dark Mode Base */
    html, body, [class*="css"]  {
        font-family: "Montserrat", sans-serif !important;
    }

    /* Fundo com gradiente radial sutil */
    .stApp {
        background-color: var(--bg);
        background-image: radial-gradient(ellipse at 75% 15%, rgba(29,122,138,.28) 0%, transparent 55%);
        color: var(--w);
    }

    /* Estilização do Header Topo Customizado */
    .hdr-dias {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 24px; border-bottom: 1px solid rgba(255,255,255,.08);
      background: rgba(0,0,0,.2);
      border-radius: 8px;
      margin-bottom: 20px;
    }
    .hdr-left { display: flex; align-items: center; }
    .logo-dias { font-size: 24px; font-weight: 900; color: var(--t1); margin-right: 16px; }
    .hdr-title { font-size: 18px; font-weight: 800; color: var(--w); text-transform: uppercase; margin-bottom: 0px; }
    .hdr-sub { font-size: 12px; color: var(--w5); }
    .kpi-pill {
      background: rgba(45,197,180,.12);
      border: 1px solid rgba(45,197,180,.3);
      border-radius: 20px;
      padding: 6px 16px;
      font-size: 14px;
      color: var(--t1);
      font-weight: 600;
    }

    /* Cards e Expanders nativos do Streamlit */
    .streamlit-expanderHeader, div[data-testid="stMetric"] {
      background: rgba(255,255,255,.04) !important;
      border: 1px solid rgba(255,255,255,.08) !important;
      border-radius: 8px !important;
      padding: 16px !important;
    }

    /* Estilizando as Métricas Nativas */
    [data-testid="stMetricValue"] { font-size: 2.0rem !important; color: var(--t1) !important; font-weight: 800 !important; }
    [data-testid="stMetricLabel"] { font-size: 1.0rem !important; color: var(--w8) !important; font-weight: 600 !important;}
    [data-testid="stMetricDelta"] { color: var(--amber) !important; }

    /* Estilizando Abas do Streamlit (para imitar o formato Dias+) */
    [data-testid="stTabs"] button {
        background: transparent !important;
        border: 1px solid rgba(255,255,255,.12) !important;
        color: var(--w5) !important;
        padding: 7px 16px !important;
        border-radius: 6px !important;
        font-family: 'Montserrat', sans-serif !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        margin-right: 6px !important;
        transition: all .2s;
    }
    [data-testid="stTabs"] button:hover {
        background: rgba(255,255,255,.06) !important; color: var(--w8) !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        background: var(--t1) !important;
        border-color: var(--t1) !important;
        color: #fff !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"] div {
        color: #fff !important;
    }
</style>
""", unsafe_allow_html=True)

# Paletas de cores para uso no Plotly
dias_teal_scale = ['#0B2E3A', '#1A5A68', '#1A8090', '#2DC5B4']
dias_red_scale = ['#0B2E3A', '#7a2826', '#a65452', '#C47A77']

# --- CARREGANDO CONFIGURAÇÕES DE LOGIN ---
with open('config.yaml', 'r', encoding='utf-8') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
)

try:
    authenticator.login(location='main')
except Exception as e:
    st.error(e)

# --- CONTROLE DE ACESSO ---
if st.session_state.get("authentication_status") == False:
    st.error('Usuário ou senha incorretos.')
elif st.session_state.get("authentication_status") is None:
    st.warning('Por favor, insira seu usuário e senha no formulário acima.')
elif st.session_state.get("authentication_status"):
    
    if 'acesso_contabilizado' not in st.session_state:
        arquivo_cont = 'acessos.json'
        if os.path.exists(arquivo_cont):
            with open(arquivo_cont, 'r', encoding='utf-8') as f:
                contadores = json.load(f)
        else:
            contadores = {}
            
        usuario = st.session_state['username']
        contadores[usuario] = contadores.get(usuario, 0) + 1
        
        with open(arquivo_cont, 'w', encoding='utf-8') as f:
            json.dump(contadores, f)
            
        st.session_state['qtd_acessos'] = contadores[usuario]
        st.session_state['acesso_contabilizado'] = True

    authenticator.logout('Sair do Sistema', 'sidebar')
    st.sidebar.markdown(f"👤 **Bem-vindo(a), {st.session_state['name']}!**")
    st.sidebar.info(f"📊 Acessos deste login: {st.session_state['qtd_acessos']}")
    st.sidebar.divider()

    # --- FUNÇÕES GLOBAIS ---
    def organizar_tabela(df_entrada):
        if df_entrada.empty: return df_entrada
        df = df_entrada.copy()
        colunas_iniciais = ['Cliente', 'Empresa', 'Canal', 'Motorista', 'Filial', 'Pedido', 'Quantidade', 'Rota']
        colunas_iniciais = [c for c in colunas_iniciais if c in df.columns]
        outras_colunas = [c for c in df.columns if c not in colunas_iniciais and str(c).lower() not in ['transportadora', 'nome_transportadora', 'desvio_logistico', 'tipo_ocorrencia', 'mes_limpo', 'mes', 'data_filtro']]
        return df[colunas_iniciais + outras_colunas]

    def gerar_pdf_dinamico(titulo, linhas_resumo, df_tabela=None):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, str(titulo).encode('latin-1', 'ignore').decode('latin-1'), ln=True, align="C")
        pdf.ln(5)
        pdf.set_font("helvetica", "", 12)
        for linha in linhas_resumo:
            pdf.cell(0, 8, str(linha).encode('latin-1', 'ignore').decode('latin-1'), ln=True)
        pdf.ln(5)
        if df_tabela is not None and not df_tabela.empty:
            pdf.set_font("helvetica", "B", 12)
            pdf.cell(0, 10, "Detalhamento (Amostra dos Principais Registros)", ln=True)
            pdf.set_font("helvetica", "B", 9)
            colunas = list(df_tabela.columns)[:4] 
            cabecalho = " | ".join([str(c)[:18] for c in colunas])
            pdf.cell(0, 8, cabecalho.encode('latin-1', 'ignore').decode('latin-1'), ln=True)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.set_font("helvetica", "", 9)
            for _, row in df_tabela.head(20).iterrows(): 
                valores = [str(row[c])[:18] for c in colunas]
                linha_val = " | ".join(valores)
                pdf.cell(0, 6, linha_val.encode('latin-1', 'ignore').decode('latin-1'), ln=True)
        return bytes(pdf.output())

    @st.cache_data(ttl=600)
    def carregar_excel_nuvem_turbinado(url, aba):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, allow_redirects=True)
        response.raise_for_status() 
        return pd.read_excel(BytesIO(response.content), sheet_name=aba, engine='openpyxl')

    # ==========================================
    # INÍCIO DO APLICATIVO
    # ==========================================
    try:
        df_danos_base, df_faltas_base, df_uni_base, df_mapa_agg, df_coord_agg, df_trat1_base, df_trat2_base = load_data()

        colunas_vitais = ['Cliente', 'Motorista', 'Filial', 'Categoria', 'Periodo', 'Tipo_Ocorrencia', 'Pedido', 'Rota', 'Quantidade', 'Empresa', 'Canal']
        for df_limpo in [df_danos_base, df_faltas_base, df_uni_base]:
            if not df_limpo.empty:
                for col in colunas_vitais:
                    if col not in df_limpo.columns: df_limpo[col] = 'Não Identificado' if col != 'Quantidade' else 0
                df_limpo['Quantidade'] = pd.to_numeric(df_limpo['Quantidade'], errors='coerce').fillna(0)
                colunas_texto = ['Cliente', 'Motorista', 'Filial', 'Categoria', 'Periodo', 'Tipo_Ocorrencia', 'Pedido', 'Rota', 'Empresa', 'Canal']
                for col in colunas_texto:
                    df_limpo[col] = df_limpo[col].astype(str).str.strip()
                    df_limpo.loc[df_limpo[col].str.lower() == 'nan', col] = 'Não Identificado'

        df_uni, df_danos, df_faltas = aplicar_filtros_barra_lateral(df_uni_base, df_danos_base, df_faltas_base)
        total_ocorrencias = len(df_uni)

        # --- HEADER DIAS+ CUSTOMIZADO EM HTML ---
        st.markdown(f"""
        <div class="hdr-dias">
          <div class="hdr-left">
            <span class="logo-dias">DIAS+</span>
            <div>
              <div class="hdr-title">PAINEL LOGÍSTICO — NATURA</div>
              <div class="hdr-sub">Visão consolidada: Danos, Faltas (NC) e Auditoria Logística · Atualizado em {pd.Timestamp.now().strftime('%d/%m/%Y às %H:%M')}</div>
            </div>
          </div>
          <div class="hdr-right">
            <div class="kpi-pill" id="pill-total">{total_ocorrencias} Ocorrências</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        menu_selecionado = option_menu(
            menu_title=None,
            options=["Resumo Executivo", "Visão Geral", "Danos", "Faltas", "Curva ABC", "Motoristas", "Clientes", "Rotas", "Tratativas", "Alertas Operacionais", "Plano de Ação", "Tendências"],
            icons=["clipboard2-data", "globe", "box-seam", "graph-down-arrow", "bar-chart-steps", "truck", "people-fill", "map", "clipboard2-check", "bell", "kanban", "graph-up-arrow"],
            default_index=0,
            orientation="horizontal",
            styles={
                "container": {
                    "padding": "4px 0",
                    "background-color": "#0B2E3A",
                    "border-bottom": "1px solid rgba(255,255,255,.08)",
                    "margin-bottom": "12px",
                },
                "icon": {"color": "#2DC5B4", "font-size": "16px"},
                "nav-link": {
                    "font-size": "12px",
                    "font-weight": "600",
                    "text-align": "center",
                    "color": "rgba(255,255,255,0.55)",
                    "--hover-color": "#1A5A68",
                    "border-radius": "6px",
                    "padding": "6px 10px",
                },
                "nav-link-selected": {
                    "background-color": "#1A8090",
                    "color": "#ffffff",
                    "border-radius": "6px",
                },
            },
        )

        if menu_selecionado == "Resumo Executivo":
            st.subheader("📋 Resumo Executivo — Natura")

            # --- DELTAS MÊS ATUAL vs ANTERIOR ---
            delta_total_str = delta_danos_str = delta_faltas_str = None
            delta_total_color = delta_danos_color = delta_faltas_color = "off"
            if 'Data_Filtro' in df_uni.columns and not df_uni.empty:
                df_dt = df_uni.copy()
                df_dt['AnoMes'] = df_dt['Data_Filtro'].dt.to_period('M')
                periodos = sorted(df_dt['AnoMes'].dropna().unique())
                if len(periodos) >= 2:
                    mes_atual, mes_ant = periodos[-1], periodos[-2]
                    n_at = len(df_dt[df_dt['AnoMes'] == mes_atual])
                    n_an = len(df_dt[df_dt['AnoMes'] == mes_ant])
                    nd_at = len(df_dt[(df_dt['AnoMes'] == mes_atual) & (df_dt['Tipo_Ocorrencia'] == 'Dano')])
                    nd_an = len(df_dt[(df_dt['AnoMes'] == mes_ant) & (df_dt['Tipo_Ocorrencia'] == 'Dano')])
                    nf_at = len(df_dt[(df_dt['AnoMes'] == mes_atual) & (df_dt['Tipo_Ocorrencia'] == 'Falta')])
                    nf_an = len(df_dt[(df_dt['AnoMes'] == mes_ant) & (df_dt['Tipo_Ocorrencia'] == 'Falta')])
                    delta_total_str = f"{n_at - n_an:+d} vs {str(mes_ant)}"
                    delta_danos_str = f"{nd_at - nd_an:+d} vs {str(mes_ant)}"
                    delta_faltas_str = f"{nf_at - nf_an:+d} vs {str(mes_ant)}"
                    delta_total_color = delta_danos_color = delta_faltas_color = "inverse"

            # --- KPIs LINHA 1 ---
            c1, c2, c3 = st.columns(3)
            c1.metric("📋 Total de Ocorrências", total_ocorrencias, delta_total_str, delta_color=delta_total_color)
            c2.metric("📦 Ocorrências de Dano", len(df_danos), delta_danos_str, delta_color=delta_danos_color)
            c3.metric("📉 Ocorrências de Falta", len(df_faltas), delta_faltas_str, delta_color=delta_faltas_color)

            # --- KPIs LINHA 2 ---
            filial_critica, qtd_filial = ("N/A", 0)
            motor_nome, motor_qtd = ("N/A", 0)
            cat_nome, cat_qtd = ("N/A", 0)
            if not df_uni.empty:
                _fil = df_uni.groupby('Filial')['Quantidade'].sum()
                filial_critica, qtd_filial = _fil.idxmax(), int(_fil.max())
                _mot = df_uni[~df_uni['Motorista'].str.upper().isin(['NÃO IDENTIFICADO','NAN',''])].groupby('Motorista')['Quantidade'].sum().nlargest(1)
                if not _mot.empty: motor_nome, motor_qtd = _mot.index[0], int(_mot.iloc[0])
                _cat = df_uni.groupby('Categoria')['Quantidade'].sum().nlargest(1)
                if not _cat.empty: cat_nome, cat_qtd = _cat.index[0], int(_cat.iloc[0])

            c4, c5, c6 = st.columns(3)
            c4.metric("🏢 Filial Mais Crítica", filial_critica, f"{qtd_filial:,} itens", delta_color="off")
            c5.metric("🚛 Motorista de Atenção", (motor_nome[:22] + "…") if len(motor_nome) > 25 else motor_nome, f"{motor_qtd:,} itens", delta_color="off")
            c6.metric("🏷️ Categoria Principal", (cat_nome[:22] + "…") if len(cat_nome) > 25 else cat_nome, f"{cat_qtd:,} itens", delta_color="off")

            st.write("---")

            # --- SEMÁFORO + INSIGHTS ---
            col_sem, col_ins = st.columns([1, 1])
            with col_sem:
                st.markdown("### 🚦 Semáforo por Filial")
                if not df_uni.empty:
                    df_sem = df_uni[df_uni['Filial'].str.upper() != 'NÃO IDENTIFICADO'].groupby('Filial')['Quantidade'].sum().reset_index()
                    q33, q66 = df_sem['Quantidade'].quantile(0.33), df_sem['Quantidade'].quantile(0.66)
                    df_sem['Status'] = df_sem['Quantidade'].apply(lambda v: "🟢 Normal" if v <= q33 else ("🟡 Atenção" if v <= q66 else "🔴 Crítico"))
                    df_sem = df_sem.sort_values('Quantidade', ascending=False).rename(columns={'Quantidade': 'Total Itens'}).reset_index(drop=True)
                    st.dataframe(df_sem[['Filial', 'Total Itens', 'Status']], use_container_width=True, hide_index=True)

            with col_ins:
                st.markdown("### 💡 Pontos de Atenção")
                pct_d = len(df_danos) / total_ocorrencias * 100 if total_ocorrencias > 0 else 0
                pct_f = len(df_faltas) / total_ocorrencias * 100 if total_ocorrencias > 0 else 0
                st.error(f"🏢 **{filial_critica}** concentra o maior volume — **{qtd_filial:,} itens** no período selecionado.")
                st.warning(f"🚛 **{motor_nome}** lidera o ranking de motoristas com **{motor_qtd:,} itens** afetados.")
                st.info(f"🏷️ Categoria **{cat_nome}** representa a maior perda física: **{cat_qtd:,} itens**.")
                tipo_pred = "Danos" if pct_d >= pct_f else "Faltas"
                pct_pred = pct_d if pct_d >= pct_f else pct_f
                st.info(f"📊 **{tipo_pred}** são o tipo predominante — **{pct_pred:.1f}%** das ocorrências.")

        elif menu_selecionado == "Visão Geral":
            if total_ocorrencias > 0:
                taxa_dano = len(df_danos) / total_ocorrencias
                taxa_falta = len(df_faltas) / total_ocorrencias
                media_itens_por_ocorrencia = df_uni["Quantidade"].sum() / total_ocorrencias
            else:
                taxa_dano = 0
                taxa_falta = 0
                media_itens_por_ocorrencia = 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total de Ocorrências", total_ocorrencias)
            c2.metric("Ocorrências de Dano", len(df_danos), f"{taxa_dano:.1%} do Total", delta_color="off")
            c3.metric("Ocorrências de Falta", len(df_faltas), f"{taxa_falta:.1%} do Total", delta_color="off")
            c4.metric("Média Itens/Ocorrência", f"{media_itens_por_ocorrencia:.1f}")
            
            st.write("---")
            
            col_esq, col_dir = st.columns([2, 1])
            with col_esq:
                st.markdown("**📊 Top 10 Motoristas (Volume de Itens)**")
                if not df_uni.empty:
                    ranking = df_uni.groupby('Motorista')['Quantidade'].sum().nlargest(10).reset_index()
                    filial_map_geral = df_uni.groupby("Motorista")["Filial"].agg(lambda x: x.value_counts().index[0] if not x.empty else "N/A").to_dict()
                    ranking["Filial"] = ranking["Motorista"].map(filial_map_geral)
                    
                    # Alterado para paleta Dias+
                    fig = px.bar(ranking, x='Quantidade', y='Motorista', orientation='h', 
                                 color='Quantidade', color_continuous_scale=dias_teal_scale,
                                 hover_data=['Filial'])
                    fig.update_layout(
                        yaxis={'categoryorder':'total ascending'}, showlegend=False, 
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                        font=dict(color='#ffffff')
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
            with col_dir:
                st.markdown("**⚖️ Dano x Falta (Itens)**")
                if not df_uni.empty:
                    pizza = df_uni.groupby('Tipo_Ocorrencia')['Quantidade'].sum().reset_index()
                    # Alterado para paleta Dias+ (Teal para dano, Vermelho para falta)
                    fig_p = px.pie(pizza, names='Tipo_Ocorrencia', values='Quantidade', hole=0.4, 
                                   color_discrete_map={'Dano':'#2DC5B4', 'Falta':'#C47A77'})
                    fig_p.update_layout(
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                        font=dict(color='#ffffff')
                    )
                    st.plotly_chart(fig_p, use_container_width=True)

            st.write("---")
            st.markdown("**🏷️ Top 10 Categorias Afetadas (Geral)**")
            if not df_uni.empty and 'Categoria' in df_uni.columns:
                cat_ranking = df_uni.groupby('Categoria')['Quantidade'].sum().nlargest(10).reset_index()
                fig_cat1 = px.bar(cat_ranking, x='Quantidade', y='Categoria', orientation='h', 
                                  color='Quantidade', color_continuous_scale=dias_teal_scale, text_auto='.0f')
                fig_cat1.update_layout(
                    yaxis={'categoryorder':'total ascending'}, showlegend=False,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff')
                )
                st.plotly_chart(fig_cat1, use_container_width=True)

            st.write("---")
            with st.expander("🔎 Ferramenta de Investigação: Explorar Dados Detalhados (Drill Down)"):
                if not df_uni.empty: st.dataframe(organizar_tabela(df_uni), use_container_width=True)
                else: st.info("Nenhum dado encontrado para os filtros atuais.")
                    
            top_geral = df_uni.groupby('Motorista')['Quantidade'].sum().nlargest(15).reset_index() if not df_uni.empty else None
            resumo_1 = [f"Total Geral: {total_ocorrencias} ocorrencias", f"Danos: {len(df_danos)}", f"Faltas: {len(df_faltas)}"]
            pdf_aba1 = gerar_pdf_dinamico("Relatorio - Visao Geral", resumo_1, top_geral)
            st.download_button("📄 Baixar Relatório: Visão Geral (PDF)", data=pdf_aba1, file_name="Visao_Geral.pdf", mime="application/pdf", key="pdf_aba1")

        elif menu_selecionado == "Danos":
            if not df_danos.empty:
                total_itens_dano = df_danos['Quantidade'].sum()
                total_ocorrencias_dano = len(df_danos)
                media_dano = total_itens_dano / total_ocorrencias_dano
                
                c1, c2, c3 = st.columns(3)
                c1.metric("📦 Volume de Itens Danificados", f"{total_itens_dano:,.0f}", "Soma de Itens")
                c2.metric("📝 Total de Registros (NC)", total_ocorrencias_dano, "Linhas na Base", delta_color="off")
                c3.metric("⚖️ Média Itens/Ocorrência", f"{media_dano:.1f}", "Itens por NC", delta_color="off")
                
                st.write("---")

                # ---- BLOCO MOTORISTA — DANOS ----
                st.markdown("### 📊 Top 10 Motoristas — Danos")
                motoristas_d = ["Todos"] + sorted([m for m in df_danos['Motorista'].unique() if str(m).upper() not in ['NÃO IDENTIFICADO', 'NAN', '']])
                motorista_sel_d = st.selectbox("🔍 Detalhar motorista:", motoristas_d, key="sel_mot_danos")

                fig_m = plot_top_motoristas(df_danos, dias_teal_scale)
                if fig_m:
                    fig_m.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                    st.plotly_chart(fig_m, use_container_width=True)

                if motorista_sel_d != "Todos":
                    df_det_mot_d = df_danos[df_danos['Motorista'] == motorista_sel_d].copy()
                    if not df_det_mot_d.empty:
                        st.markdown(f"#### 📈 Evolução Mensal — {motorista_sel_d}")
                        if 'Data_Filtro' in df_det_mot_d.columns:
                            df_det_mot_d['Mês'] = df_det_mot_d['Data_Filtro'].dt.strftime('%m/%Y')
                            ev_d = df_det_mot_d.groupby('Mês')['Quantidade'].sum().reset_index()
                            ev_d['_sort'] = pd.to_datetime(ev_d['Mês'], format='%m/%Y', errors='coerce')
                            ev_d = ev_d.sort_values('_sort').drop(columns='_sort')
                            fig_ev_d = px.line(ev_d, x='Mês', y='Quantidade', markers=True,
                                               color_discrete_sequence=['#2DC5B4'],
                                               labels={'Quantidade': 'Itens Danificados'})
                            fig_ev_d.update_traces(line_width=2.5, marker_size=8)
                            fig_ev_d.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                            st.plotly_chart(fig_ev_d, use_container_width=True)
                        st.markdown(f"#### 📋 Registros — {motorista_sel_d}")
                        df_tab_mot_d = organizar_tabela(df_det_mot_d)
                        cols_det_d = [c for c in ["Motorista", "Filial", "Quantidade", "descricao_ocorrencia", "Cliente", "Pedido", "Tipo_Ocorrencia"] if c in df_tab_mot_d.columns]
                        st.dataframe(df_tab_mot_d[cols_det_d + [c for c in df_tab_mot_d.columns if c not in cols_det_d]], use_container_width=True)

                st.write("---")

                # ---- BLOCO FILIAL — DANOS ----
                st.markdown("### 🏢 Volume de Danos por Filial")
                filiais_d = ["Todas"] + sorted([f for f in df_danos['Filial'].unique() if str(f).upper() not in ['NÃO IDENTIFICADO', 'NAN', '']])
                filial_sel_d = st.selectbox("🔍 Detalhar filial:", filiais_d, key="sel_fil_danos")

                fig_f = plot_comparativo_filial(df_danos, dias_teal_scale)
                if fig_f:
                    fig_f.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                    st.plotly_chart(fig_f, use_container_width=True)

                if filial_sel_d != "Todas":
                    df_det_fil_d = df_danos[df_danos['Filial'] == filial_sel_d].copy()
                    if not df_det_fil_d.empty:
                        st.markdown(f"#### 📈 Evolução Mensal — Filial {filial_sel_d}")
                        if 'Data_Filtro' in df_det_fil_d.columns:
                            df_det_fil_d['Mês'] = df_det_fil_d['Data_Filtro'].dt.strftime('%m/%Y')
                            ev_fd = df_det_fil_d.groupby('Mês')['Quantidade'].sum().reset_index()
                            ev_fd['_sort'] = pd.to_datetime(ev_fd['Mês'], format='%m/%Y', errors='coerce')
                            ev_fd = ev_fd.sort_values('_sort').drop(columns='_sort')
                            fig_ev_fd = px.line(ev_fd, x='Mês', y='Quantidade', markers=True,
                                                color_discrete_sequence=['#2DC5B4'],
                                                labels={'Quantidade': 'Itens Danificados'})
                            fig_ev_fd.update_traces(line_width=2.5, marker_size=8)
                            fig_ev_fd.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                            st.plotly_chart(fig_ev_fd, use_container_width=True)
                        st.markdown(f"#### 📋 Registros — Filial {filial_sel_d}")
                        df_tab_fil_d = organizar_tabela(df_det_fil_d)
                        cols_det_fd = [c for c in ["Motorista", "Filial", "Quantidade", "descricao_ocorrencia", "Cliente", "Pedido", "Tipo_Ocorrencia"] if c in df_tab_fil_d.columns]
                        st.dataframe(df_tab_fil_d[cols_det_fd + [c for c in df_tab_fil_d.columns if c not in cols_det_fd]], use_container_width=True)

                st.write("---")
                st.markdown("### 🏷️ Categorias com Mais Danos")
                if 'Categoria' in df_danos.columns:
                    cat_danos = df_danos.groupby('Categoria')['Quantidade'].sum().nlargest(10).reset_index()
                    fig_cat2 = px.bar(cat_danos, x='Quantidade', y='Categoria', orientation='h', 
                                      color='Quantidade', color_continuous_scale=dias_teal_scale, text_auto='.0f')
                    fig_cat2.update_layout(
                        yaxis={'categoryorder':'total ascending'}, showlegend=False,
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff')
                    )
                    st.plotly_chart(fig_cat2, use_container_width=True)
            
            st.markdown("### 📋 Tabela Organizada - Danos")
            if not df_danos.empty:
                df_tabela_formatada = organizar_tabela(df_danos)
                colunas_exibicao = [c for c in ["Motorista", "Filial", "Quantidade", "descricao_ocorrencia", "Cliente", "Pedido", "Tipo_Ocorrencia"] if c in df_tabela_formatada.columns]
                df_exibicao = df_tabela_formatada[colunas_exibicao + [c for c in df_tabela_formatada.columns if c not in colunas_exibicao]]
                st.dataframe(df_exibicao, use_container_width=True)
            else:
                st.info("Nenhum dado de dano encontrado para os filtros atuais.")
                
            top_danos = df_danos.groupby('Motorista')['Quantidade'].sum().nlargest(15).reset_index() if not df_danos.empty else None
            resumo_2 = [f"Ocorrencias Exclusivas de Dano: {len(df_danos)} registros vinculados."]
            pdf_aba2 = gerar_pdf_dinamico("Relatorio - Somente Danos", resumo_2, top_danos)
            st.download_button("📄 Baixar Relatório: Danos (PDF)", data=pdf_aba2, file_name="Relatorio_Danos.pdf", mime="application/pdf", key="pdf_aba2")

            st.write("---")
            st.subheader("📥 Relatório Executivo para Diretoria — Top 10 Ofensores (Danos)")
            if not df_danos.empty and 'Data_Filtro' in df_danos.columns:
                df_danos_rep = df_danos.copy()
                df_danos_rep['Mês'] = df_danos_rep['Data_Filtro'].dt.strftime('%m/%Y')
                top10_mot_d = df_danos_rep.groupby('Motorista')['Quantidade'].sum().nlargest(10).index
                df_top10_d = df_danos_rep[df_danos_rep['Motorista'].isin(top10_mot_d)]
                tabela_dir_d = pd.pivot_table(
                    df_top10_d,
                    values='Quantidade',
                    index=['Motorista', 'Filial'],
                    columns='Mês',
                    aggfunc='sum',
                    fill_value=0
                )
                tabela_dir_d['Total'] = tabela_dir_d.sum(axis=1)
                tabela_dir_d = tabela_dir_d.sort_values(by='Total', ascending=False)
                st.dataframe(tabela_dir_d, use_container_width=True)
                output_d = BytesIO()
                with pd.ExcelWriter(output_d, engine='xlsxwriter') as writer:
                    tabela_dir_d.to_excel(writer, sheet_name='Top 10 Ofensores - Danos')
                    ws = writer.sheets['Top 10 Ofensores - Danos']
                    ws.set_column('A:A', 35)
                    ws.set_column('B:B', 25)
                st.download_button(
                    label="📊 Baixar Relatório Formatado (Excel)",
                    data=output_d.getvalue(),
                    file_name='Relatorio_Danos_Diretoria.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    key='excel_danos'
                )
            else:
                st.warning("Coluna de data não disponível para gerar o relatório.")

        elif menu_selecionado == "Faltas":
            if not df_faltas.empty:
                total_itens_falta = df_faltas['Quantidade'].sum()
                total_ocorrencias_falta = len(df_faltas)
                media_falta = total_itens_falta / total_ocorrencias_falta
                
                c1, c2, c3 = st.columns(3)
                c1.metric("📦 Volume de Itens Faltantes", f"{total_itens_falta:,.0f}", "Soma de Itens")
                c2.metric("📝 Total de Registros (NC)", total_ocorrencias_falta, "Linhas na Base", delta_color="off")
                c3.metric("⚖️ Média Itens/Ocorrência", f"{media_falta:.1f}", "Itens por NC", delta_color="off")
                
                st.write("---")

                # ---- BLOCO MOTORISTA — FALTAS ----
                st.markdown("### 📊 Top 10 Motoristas — Faltas")
                motoristas_f = ["Todos"] + sorted([m for m in df_faltas['Motorista'].unique() if str(m).upper() not in ['NÃO IDENTIFICADO', 'NAN', '']])
                motorista_sel_f = st.selectbox("🔍 Detalhar motorista:", motoristas_f, key="sel_mot_faltas")

                df_mot_falta = df_faltas.groupby('Motorista')['Quantidade'].sum().nlargest(10).reset_index()
                filial_map = df_faltas.groupby("Motorista")["Filial"].agg(lambda x: x.value_counts().index[0] if not x.empty else "Não Identificado").to_dict()
                df_mot_falta["Filial"] = df_mot_falta["Motorista"].map(filial_map)
                fig_m = px.bar(df_mot_falta, x='Quantidade', y='Motorista', orientation='h', color='Quantidade', color_continuous_scale=dias_red_scale, text_auto='.0f', hover_data=['Filial'])
                fig_m.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                st.plotly_chart(fig_m, use_container_width=True)

                if motorista_sel_f != "Todos":
                    df_det_mot_f = df_faltas[df_faltas['Motorista'] == motorista_sel_f].copy()
                    if not df_det_mot_f.empty:
                        st.markdown(f"#### 📈 Evolução Mensal — {motorista_sel_f}")
                        if 'Data_Filtro' in df_det_mot_f.columns:
                            df_det_mot_f['Mês'] = df_det_mot_f['Data_Filtro'].dt.strftime('%m/%Y')
                            ev_f = df_det_mot_f.groupby('Mês')['Quantidade'].sum().reset_index()
                            ev_f['_sort'] = pd.to_datetime(ev_f['Mês'], format='%m/%Y', errors='coerce')
                            ev_f = ev_f.sort_values('_sort').drop(columns='_sort')
                            fig_ev_f = px.line(ev_f, x='Mês', y='Quantidade', markers=True,
                                               color_discrete_sequence=['#C47A77'],
                                               labels={'Quantidade': 'Itens Faltantes'})
                            fig_ev_f.update_traces(line_width=2.5, marker_size=8)
                            fig_ev_f.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                            st.plotly_chart(fig_ev_f, use_container_width=True)
                        st.markdown(f"#### 📋 Registros — {motorista_sel_f}")
                        df_tab_mot_f = organizar_tabela(df_det_mot_f)
                        cols_det_mf = [c for c in ["Motorista", "Filial", "Quantidade", "descricao_ocorrencia", "Cliente", "Pedido", "Tipo_Ocorrencia"] if c in df_tab_mot_f.columns]
                        st.dataframe(df_tab_mot_f[cols_det_mf + [c for c in df_tab_mot_f.columns if c not in cols_det_mf]], use_container_width=True)

                st.write("---")

                # ---- BLOCO FILIAL — FALTAS ----
                st.markdown("### 🏢 Volume de Faltas por Filial")
                filiais_f = ["Todas"] + sorted([f for f in df_faltas['Filial'].unique() if str(f).upper() not in ['NÃO IDENTIFICADO', 'NAN', '']])
                filial_sel_f = st.selectbox("🔍 Detalhar filial:", filiais_f, key="sel_fil_faltas")

                df_fil_falta = df_faltas.groupby('Filial')['Quantidade'].sum().sort_values(ascending=False).reset_index()
                fig_f = px.bar(df_fil_falta, x='Filial', y='Quantidade', color='Quantidade', color_continuous_scale=dias_red_scale, text_auto='.0f')
                fig_f.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                st.plotly_chart(fig_f, use_container_width=True)

                if filial_sel_f != "Todas":
                    df_det_fil_f = df_faltas[df_faltas['Filial'] == filial_sel_f].copy()
                    if not df_det_fil_f.empty:
                        st.markdown(f"#### 📈 Evolução Mensal — Filial {filial_sel_f}")
                        if 'Data_Filtro' in df_det_fil_f.columns:
                            df_det_fil_f['Mês'] = df_det_fil_f['Data_Filtro'].dt.strftime('%m/%Y')
                            ev_ff = df_det_fil_f.groupby('Mês')['Quantidade'].sum().reset_index()
                            ev_ff['_sort'] = pd.to_datetime(ev_ff['Mês'], format='%m/%Y', errors='coerce')
                            ev_ff = ev_ff.sort_values('_sort').drop(columns='_sort')
                            fig_ev_ff = px.line(ev_ff, x='Mês', y='Quantidade', markers=True,
                                                color_discrete_sequence=['#C47A77'],
                                                labels={'Quantidade': 'Itens Faltantes'})
                            fig_ev_ff.update_traces(line_width=2.5, marker_size=8)
                            fig_ev_ff.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                            st.plotly_chart(fig_ev_ff, use_container_width=True)
                        st.markdown(f"#### 📋 Registros — Filial {filial_sel_f}")
                        df_tab_fil_f = organizar_tabela(df_det_fil_f)
                        cols_det_ff = [c for c in ["Motorista", "Filial", "Quantidade", "descricao_ocorrencia", "Cliente", "Pedido", "Tipo_Ocorrencia"] if c in df_tab_fil_f.columns]
                        st.dataframe(df_tab_fil_f[cols_det_ff + [c for c in df_tab_fil_f.columns if c not in cols_det_ff]], use_container_width=True)

                st.write("---")

                st.markdown("### 🏷️ Categorias com Maior Perda Física")
                if 'Categoria' in df_faltas.columns:
                    cat_faltas = df_faltas.groupby('Categoria')['Quantidade'].sum().nlargest(10).reset_index()
                    fig_cat3 = px.bar(cat_faltas, x='Quantidade', y='Categoria', orientation='h', color='Quantidade', color_continuous_scale=dias_red_scale, text_auto='.0f')
                    fig_cat3.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                    st.plotly_chart(fig_cat3, use_container_width=True)
            
            st.markdown("### 📋 Tabela Organizada - Faltas")
            if not df_faltas.empty:
                df_tabela_formatada = organizar_tabela(df_faltas)
                colunas_exibicao = [c for c in ["Motorista", "Filial", "Quantidade", "descricao_ocorrencia", "Cliente", "Pedido", "Tipo_Ocorrencia"] if c in df_tabela_formatada.columns]
                df_exibicao = df_tabela_formatada[colunas_exibicao + [c for c in df_tabela_formatada.columns if c not in colunas_exibicao]]
                st.dataframe(df_exibicao, use_container_width=True)
            else:
                st.info("Nenhum dado de falta encontrado.")

            st.write("---")
            st.subheader("📥 Relatório Executivo para Diretoria — Top 10 Ofensores (Faltas)")
            if not df_faltas.empty and 'Data_Filtro' in df_faltas.columns:
                df_faltas_rep = df_faltas.copy()
                df_faltas_rep['Mês'] = df_faltas_rep['Data_Filtro'].dt.strftime('%m/%Y')
                top10_mot_f = df_faltas_rep.groupby('Motorista')['Quantidade'].sum().nlargest(10).index
                df_top10_f = df_faltas_rep[df_faltas_rep['Motorista'].isin(top10_mot_f)]
                tabela_dir_f = pd.pivot_table(
                    df_top10_f,
                    values='Quantidade',
                    index=['Motorista', 'Filial'],
                    columns='Mês',
                    aggfunc='sum',
                    fill_value=0
                )
                tabela_dir_f['Total'] = tabela_dir_f.sum(axis=1)
                tabela_dir_f = tabela_dir_f.sort_values(by='Total', ascending=False)
                st.dataframe(tabela_dir_f, use_container_width=True)
                output_f = BytesIO()
                with pd.ExcelWriter(output_f, engine='xlsxwriter') as writer:
                    tabela_dir_f.to_excel(writer, sheet_name='Top 10 Ofensores - Faltas')
                    ws = writer.sheets['Top 10 Ofensores - Faltas']
                    ws.set_column('A:A', 35)
                    ws.set_column('B:B', 25)
                st.download_button(
                    label="📊 Baixar Relatório Formatado (Excel)",
                    data=output_f.getvalue(),
                    file_name='Relatorio_Faltas_Diretoria.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    key='excel_faltas'
                )
            else:
                st.warning("Coluna de data não disponível para gerar o relatório.")

        elif menu_selecionado == "Curva ABC":
            st.subheader("🎯 Curva ABC por Motorista (Reativa)")
            fig_abc, df_abc = plot_curva_abc(df_uni)
            if fig_abc:
                fig_abc.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                st.plotly_chart(fig_abc, use_container_width=True)
                st.dataframe(df_abc, use_container_width=True)
            else: st.info("Aguardando dados filtrados para calcular a Curva ABC.")
            
            resumo_4 = ["Classificacao de ofensores pelo metodo ABC (Filtro aplicado na lateral)."]
            pdf_aba4 = gerar_pdf_dinamico("Relatorio - Curva ABC", resumo_4, df_abc)
            st.download_button("📄 Baixar Relatório: Curva ABC (PDF)", data=pdf_aba4, file_name="Curva_ABC.pdf", mime="application/pdf", key="pdf_aba4")

        elif menu_selecionado == "Motoristas":
            st.subheader("🔄 Histórico Mensal de Ofensores (Motoristas)")
            if not df_uni.empty:
                df_mot_valido = df_uni[~df_uni['Motorista'].str.upper().isin(['NÃO IDENTIFICADO', 'NAN', '', 'N/A'])].copy()
                resumo_recorrencia_m = df_mot_valido.groupby('Motorista').agg(
                    Qtd_Periodos=('Periodo', 'nunique'), Total_Itens=('Quantidade', 'sum')
                ).reset_index().sort_values(by=['Total_Itens', 'Qtd_Periodos'], ascending=[False, False])
                
                top_motoristas = resumo_recorrencia_m.head(15)['Motorista'].tolist()
                df_uni_top_mot = df_mot_valido[df_mot_valido['Motorista'].isin(top_motoristas)]
                
                fig_heat_m, df_recor_m = plot_heatmap_recorrencia(df_uni_top_mot, 'Motorista')
                if fig_heat_m:
                    fig_heat_m.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                    st.plotly_chart(fig_heat_m, use_container_width=True)
                    
                    st.markdown("**📋 Motoristas de Atenção — Visão Consolidada:**")
                    df_resumo_mot = df_uni_top_mot.pivot_table(index='Motorista', columns='Tipo_Ocorrencia', values='Quantidade', aggfunc='sum', fill_value=0).reset_index()
                    if 'Dano' not in df_resumo_mot.columns: df_resumo_mot['Dano'] = 0
                    if 'Falta' not in df_resumo_mot.columns: df_resumo_mot['Falta'] = 0
                    
                    df_resumo_mot['Total de Itens'] = df_resumo_mot['Dano'] + df_resumo_mot['Falta']
                    df_resumo_mot = pd.merge(df_resumo_mot, resumo_recorrencia_m[['Motorista', 'Qtd_Periodos']], on='Motorista', how='left')
                    df_resumo_mot = df_resumo_mot.sort_values(by=['Qtd_Periodos', 'Total de Itens'], ascending=[False, False]).reset_index(drop=True)
                    df_resumo_mot = df_resumo_mot.rename(columns={'Dano': '📦 Itens Danificados', 'Falta': '📉 Itens Faltantes', 'Qtd_Periodos': '📅 Meses Afetados'})
                    st.dataframe(df_resumo_mot, use_container_width=True)
                else: 
                    st.info("Ajuste os filtros para visualizar a recorrência.")
                    df_resumo_mot = None
            else:
                st.info("Base de dados vazia para os filtros atuais.")
                df_resumo_mot = None
                
            resumo_5 = ["Acompanhamento dos Motoristas mais críticos."]
            pdf_aba5 = gerar_pdf_dinamico("Dossiê - Motoristas Críticos", resumo_5, df_resumo_mot if df_resumo_mot is not None else None)
            st.download_button("📄 Baixar Relatório: Recor. Motorista (PDF)", data=pdf_aba5, file_name="Recorrencia_Motoristas.pdf", mime="application/pdf", key="pdf_aba5")

        elif menu_selecionado == "Clientes":
            st.subheader("🔄 Histórico Mensal de Clientes Reincidentes")
            if not df_uni.empty:
                df_cli_valido = df_uni[~df_uni['Cliente'].str.upper().isin(['NÃO IDENTIFICADO', 'NAN', '', 'N/A'])].copy()
                resumo_recorrencia = df_cli_valido.groupby('Cliente').agg(
                    Qtd_Periodos=('Periodo', 'nunique'), Total_Itens=('Quantidade', 'sum')
                ).reset_index().sort_values(by=['Total_Itens', 'Qtd_Periodos'], ascending=[False, False])

                top_clientes = resumo_recorrencia.head(15)['Cliente'].tolist()
                df_uni_top_clientes = df_cli_valido[df_cli_valido['Cliente'].isin(top_clientes)]
                
                fig_heat_c, df_recor_c = plot_heatmap_recorrencia(df_uni_top_clientes, 'Cliente')
                
                if fig_heat_c: 
                    fig_heat_c.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                    st.plotly_chart(fig_heat_c, use_container_width=True)
                    
                    st.markdown("**📋 Clientes Críticos — Visão Consolidada:**")
                    df_resumo_cli = df_uni_top_clientes.pivot_table(index='Cliente', columns='Tipo_Ocorrencia', values='Quantidade', aggfunc='sum', fill_value=0).reset_index()
                    if 'Dano' not in df_resumo_cli.columns: df_resumo_cli['Dano'] = 0
                    if 'Falta' not in df_resumo_cli.columns: df_resumo_cli['Falta'] = 0
                    
                    df_resumo_cli['Total de Itens'] = df_resumo_cli['Dano'] + df_resumo_cli['Falta']
                    df_resumo_cli = pd.merge(df_resumo_cli, resumo_recorrencia[['Cliente', 'Qtd_Periodos']], on='Cliente', how='left')
                    df_resumo_cli = df_resumo_cli.sort_values(by=['Qtd_Periodos', 'Total de Itens'], ascending=[False, False]).reset_index(drop=True)
                    df_resumo_cli = df_resumo_cli.rename(columns={'Dano': '📦 Itens Danificados', 'Falta': '📉 Itens Faltantes', 'Qtd_Periodos': '📅 Meses Afetados'})
                    st.dataframe(df_resumo_cli, use_container_width=True)
                else: 
                    st.info("Nenhum cliente válido para análise na seleção atual.")
                    df_resumo_cli = None
            else:
                st.info("Base de dados vazia para os filtros atuais.")
                df_resumo_cli = None
                
            resumo_6 = ["Acompanhamento dos Clientes mais críticos."]
            pdf_aba6 = gerar_pdf_dinamico("Dossie - Clientes Criticos", resumo_6, df_resumo_cli if df_resumo_cli is not None else None)
            st.download_button("📄 Baixar Relatório: Recor. Cliente (PDF)", data=pdf_aba6, file_name="Recorrencia_Clientes.pdf", mime="application/pdf", key="pdf_aba6")

        elif menu_selecionado == "Rotas":
            st.subheader("📍 Detalhamento e Inteligência por Rota")
            coluna_rota_real = None
            for col in df_uni.columns:
                if col.lower() == 'rota':
                    coluna_rota_real = col
                    break
                    
            if coluna_rota_real:
                if not df_danos.empty and coluna_rota_real in df_danos.columns:
                    df_danos_rota = df_danos.groupby(coluna_rota_real)['Quantidade'].sum().reset_index(name='Qtd_Danos')
                else: df_danos_rota = pd.DataFrame(columns=[coluna_rota_real, 'Qtd_Danos'])
                    
                if not df_faltas.empty and coluna_rota_real in df_faltas.columns:
                    df_faltas_rota = df_faltas.groupby(coluna_rota_real)['Quantidade'].sum().reset_index(name='Qtd_Faltas')
                else: df_faltas_rota = pd.DataFrame(columns=[coluna_rota_real, 'Qtd_Faltas'])
                    
                df_resumo_rotas = pd.merge(df_danos_rota, df_faltas_rota, on=coluna_rota_real, how='outer').fillna(0)
                df_resumo_rotas['Qtd_Danos'] = df_resumo_rotas['Qtd_Danos'].astype(int)
                df_resumo_rotas['Qtd_Faltas'] = df_resumo_rotas['Qtd_Faltas'].astype(int)
                df_resumo_rotas['Total_Volume'] = df_resumo_rotas['Qtd_Danos'] + df_resumo_rotas['Qtd_Faltas']
                df_resumo_rotas['rota_padrao'] = df_resumo_rotas[coluna_rota_real].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

                if not df_mapa_agg.empty:
                    df_mapa_agg['Rota'] = df_mapa_agg['Rota'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                    df_final = pd.merge(df_resumo_rotas, df_mapa_agg, left_on='rota_padrao', right_on='Rota', how='left')
                    df_final['Cidade'] = df_final['Cidade'].fillna('Não Identificada')
                    df_final['Bairro'] = df_final['Bairro'].fillna('Não Identificado')
                else:
                    df_final = df_resumo_rotas.copy()
                    df_final['Cidade'] = 'Sem dados'
                    df_final['Bairro'] = 'Sem dados'

                df_final = df_final[df_final['Total_Volume'] > 0].sort_values(by='Total_Volume', ascending=False).reset_index(drop=True)

                st.markdown("### 📋 Tabela de Ofensores por Rota")
                colunas_exibicao = ['rota_padrao', 'Cidade', 'Bairro', 'Qtd_Danos', 'Qtd_Faltas', 'Total_Volume']
                df_exibicao = df_final[[c for c in colunas_exibicao if c in df_final.columns]].rename(columns={'rota_padrao': 'Rota'}).copy()
                st.dataframe(df_exibicao, use_container_width=True)

                st.write("---")
                st.markdown("### 🌍 Inteligência Geográfica de Ocorrências")
                df_geo = df_uni.copy()
                
                if not df_mapa_agg.empty:
                    df_geo['rota_padrao'] = df_geo[coluna_rota_real].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                    df_mapa_agg_clean = df_mapa_agg.copy()
                    df_mapa_agg_clean['Rota'] = df_mapa_agg_clean['Rota'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                    
                    df_geo = pd.merge(df_geo, df_mapa_agg_clean[['Rota', 'Cidade', 'Bairro']], left_on='rota_padrao', right_on='Rota', how='left')
                    df_geo['Cidade'] = df_geo['Cidade'].fillna('Não Identificada')
                    df_geo['Bairro'] = df_geo['Bairro'].fillna('Não Identificado')
                    df_geo = df_geo[df_geo['Quantidade'] > 0]

                    col_cid, col_bai = st.columns(2)
                    with col_cid:
                        st.markdown("#### 🏆 Top 10 Cidades Críticas")
                        top_cidades = df_geo.groupby('Cidade')['Quantidade'].sum().nlargest(10).reset_index()
                        fig_cid = px.bar(top_cidades, x='Quantidade', y='Cidade', orientation='h', color='Quantidade', color_continuous_scale=dias_teal_scale, text_auto='.0f')
                        fig_cid.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                        st.plotly_chart(fig_cid, use_container_width=True)

                    with col_bai:
                        st.markdown("#### 🚨 Top 10 Bairros Críticos")
                        df_bairros = df_geo[df_geo['Bairro'] != 'Não Identificado']
                        top_bairros = df_bairros.groupby('Bairro')['Quantidade'].sum().nlargest(10).reset_index()
                        fig_bai = px.bar(top_bairros, x='Quantidade', y='Bairro', orientation='h', color='Quantidade', color_continuous_scale=dias_red_scale, text_auto='.0f')
                        fig_bai.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
                        st.plotly_chart(fig_bai, use_container_width=True)

                else:
                    st.warning("⚠️ Para visualizar a inteligência geográfica, as informações do arquivo 'relatorionotas.csv' precisam estar carregadas corretamente.")

            else:
                st.error("Aviso: A coluna de rotas não foi encontrada na base de dados principal.")
                
        elif menu_selecionado == "Tratativas":
    st.subheader("📝 Controle de Tratativas")
    
    # Link visual para o usuário abrir no navegador
    link_visualizacao = "https://docs.google.com/spreadsheets/d/12PurxfsZrm7YH8VP3EU2kyIJ-G7cVbt_CEj2l8cXsJQ/edit?usp=sharing"
    
    # Link técnico em formato XLSX para o Pandas conseguir ler as abas "Danos" e "Faltas"
    link_download = "https://docs.google.com/spreadsheets/d/12PurxfsZrm7YH8VP3EU2kyIJ-G7cVbt_CEj2l8cXsJQ/export?format=xlsx"
    
    st.link_button("Abrir Planilha de Tratativas", link_visualizacao)

    st.markdown("### 📦 Tratativas - Danos")
    df_exibicao_danos = None
    
    try:
        with st.spinner("Sincronizando Danos com o Google Sheets..."):
            # Usando o link_download aqui
            df_tratativas_danos = carregar_excel_nuvem_turbinado(link_download, "Danos").dropna(how='all').reset_index(drop=True)
        st.success(f"✅ {len(df_tratativas_danos)} registros de Danos carregados do Google Sheets.")

        c_t1, c_t2, c_t3 = st.columns(3)
        c_t1.metric("📋 Total de Registros", len(df_tratativas_danos))
        c_t2.metric("📁 Colunas Disponíveis", len(df_tratativas_danos.columns))
        c_t3.metric("📊 Filiais Envolvidas", df_tratativas_danos['filial'].nunique() if 'filial' in df_tratativas_danos.columns else "—")

        with st.expander("⚙️ Escolher colunas para exibir (Danos)", expanded=False):
            todas_colunas_danos = df_tratativas_danos.columns.tolist()
            colunas_selecionadas_danos = st.multiselect("Selecione as colunas desejadas:", options=todas_colunas_danos, default=todas_colunas_danos, key="multi_danos")

        df_exibicao_danos = df_tratativas_danos[colunas_selecionadas_danos]
        st.dataframe(df_exibicao_danos, use_container_width=True)

    except Exception as e:
        st.warning("⏳ Falha ao carregar a nuvem. Verifique as permissões do link.")
        st.info(f"Detalhe técnico: {e}")

    st.write("---") 

    st.markdown("### 🛍️ Tratativas - Faltas")
    df_exibicao_faltas = None
    
    try:
        with st.spinner("Sincronizando Faltas com o Google Sheets..."):
            # Usando o link_download aqui também
            df_tratativas_faltas = carregar_excel_nuvem_turbinado(link_download, "Faltas").dropna(how='all').reset_index(drop=True)
        st.success(f"✅ {len(df_tratativas_faltas)} registros de Faltas carregados do Google Sheets.")

        c_t4, c_t5, c_t6 = st.columns(3)
        c_t4.metric("📋 Total de Registros", len(df_tratativas_faltas))
        c_t5.metric("📁 Colunas Disponíveis", len(df_tratativas_faltas.columns))
        c_t6.metric("📊 Filiais Envolvidas", df_tratativas_faltas['filial'].nunique() if 'filial' in df_tratativas_faltas.columns else "—")

        with st.expander("⚙️ Escolher colunas para exibir (Faltas)", expanded=False):
            todas_colunas_faltas = df_tratativas_faltas.columns.tolist()
            colunas_selecionadas_faltas = st.multiselect("Selecione as colunas desejadas:", options=todas_colunas_faltas, default=todas_colunas_faltas, key="multi_faltas")

        df_exibicao_faltas = df_tratativas_faltas[colunas_selecionadas_faltas]
        st.dataframe(df_exibicao_faltas, use_container_width=True)

    except Exception as e:
        st.error("⚠️ Erro ao conectar com a sua planilha na nuvem.")
        st.info(f"Detalhe técnico: {e}")
        
    st.write("---")
    resumo_8 = ["Extracao rapida do controle online de tratativas e ressarcimentos."]
    df_pdf_8 = df_exibicao_danos if df_exibicao_danos is not None else df_exibicao_faltas
    pdf_aba8 = gerar_pdf_dinamico("Controle de Tratativas (Nuvem)", resumo_8, df_pdf_8)
    st.download_button(label="📄 Baixar Relatório: Tratativas (PDF)", data=pdf_aba8, file_name="Controle_Tratativas.pdf", mime="application/pdf", key="pdf_aba8")
        elif menu_selecionado == "Alertas Operacionais":
            st.subheader("⚠️ Alertas Operacionais — Análise de Anomalias")

            if not df_uni.empty:
                df_cli = df_uni[~df_uni['Cliente'].str.upper().isin(['NÃO IDENTIFICADO', 'NAN', ''])].copy()

                # --- SLIDERS DE CONFIGURAÇÃO ---
                st.markdown("#### ⚙️ Parâmetros de Detecção")
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    limiar_volume = st.slider("📦 Volume atípico (itens)", min_value=10, max_value=200, value=50, step=5,
                                              help="Pedidos com quantidade acima deste valor são sinalizados.")
                with col_s2:
                    limiar_freq = st.slider("🔁 Recorrência mínima (ocorrências por cliente)", min_value=2, max_value=10, value=2, step=1,
                                            help="Clientes com este número ou mais de ocorrências no período são sinalizados.")
                with col_s3:
                    limiar_mot = st.slider("🚛 Abrangência do motorista (clientes distintos)", min_value=5, max_value=50, value=20, step=5,
                                           help="Motoristas que afetaram este número ou mais de clientes distintos são sinalizados.")

                st.write("---")

                # --- REGRA 1: VOLUME ATÍPICO ---
                f_vol = df_cli[df_cli['Quantidade'] >= limiar_volume].copy()
                f_vol['Alerta'] = 'Volume Atípico'

                # --- REGRA 2: CLIENTE RECORRENTE ---
                freq_cli = df_cli.groupby('Cliente').size().reset_index(name='Ocorrencias')
                clientes_recorrentes = freq_cli[freq_cli['Ocorrencias'] >= limiar_freq]['Cliente']
                f_rep = df_cli[df_cli['Cliente'].isin(clientes_recorrentes)].copy()
                f_rep['Alerta'] = 'Cliente Recorrente'

                # --- REGRA 3: ALTA ABRANGÊNCIA DE CLIENTES POR MOTORISTA ---
                mot_abrangencia = df_cli.groupby('Motorista')['Cliente'].nunique().reset_index(name='Qtd_Clientes')
                lista_mot = mot_abrangencia[mot_abrangencia['Qtd_Clientes'] >= limiar_mot]['Motorista']
                f_mot = df_cli[df_cli['Motorista'].isin(lista_mot)].copy()
                f_mot['Alerta'] = 'Alta Abrangência de Clientes'

                # --- REGRA 4: TERMOS INDICATIVOS NA DESCRIÇÃO ---
                f_isento = pd.DataFrame()
                coluna_texto = 'description'
                if coluna_texto in df_cli.columns:
                    termos_origem = [
                        r'falta de volume', r'volume (inteiro|faltante)', r'sacola',
                        r'presente', r'trocado', r'Volume faltante(s)', r'SACOLA PRESENTE', r'inversão'
                    ]
                    padrao_busca = '|'.join(termos_origem)
                    f_isento = df_cli[df_cli[coluna_texto].str.contains(padrao_busca, case=False, na=False, regex=True)].copy()
                    if not f_isento.empty:
                        f_isento['Alerta'] = 'Indicativo de Origem'

                alertas = pd.concat([f_vol, f_rep, f_mot, f_isento])

                if not alertas.empty:
                    alertas = alertas.drop_duplicates(subset=['Pedido', 'Alerta'])
                    alertas = alertas.loc[:, ~alertas.columns.duplicated()]
                    total_itens = alertas['Quantidade'].sum()

                    # --- KPI CARDS POR CATEGORIA ---
                    n_vol = len(f_vol.drop_duplicates(subset=['Pedido']))
                    n_rep = len(f_rep.drop_duplicates(subset=['Pedido']))
                    n_mot = len(f_mot.drop_duplicates(subset=['Pedido']))
                    n_ise = len(f_isento.drop_duplicates(subset=['Pedido'])) if not f_isento.empty else 0

                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("⚠️ Total de Alertas", len(alertas.drop_duplicates(subset=['Pedido'])))
                    c2.metric("📦 Volume Atípico", n_vol, f"≥ {limiar_volume} itens")
                    c3.metric("🔁 Clientes Recorrentes", n_rep, f"≥ {limiar_freq} ocorr.")
                    c4.metric("🚛 Alta Abrangência", n_mot, f"≥ {limiar_mot} clientes")
                    c5.metric("🏷️ Indicativo Origem", n_ise, "termos detectados")

                    st.write("---")
                    st.markdown(f"### 📋 Registros Sinalizados — {len(alertas.drop_duplicates(subset=['Pedido']))} pedidos | {total_itens:,.0f} itens envolvidos")

                    colunas_exibicao = ['Alerta', 'Cliente', 'Pedido', 'Quantidade', 'Tipo_Ocorrencia', 'Motorista', 'Filial', 'Canal', 'description']
                    colunas_existentes = [col for col in colunas_exibicao if col in alertas.columns]
                    df_exibicao = alertas[colunas_existentes].copy()
                    st.dataframe(df_exibicao, use_container_width=True)
                else:
                    st.success("✅ Nenhuma anomalia detectada com os parâmetros atuais.")

        elif menu_selecionado == "Plano de Ação":
            st.subheader("📋 Plano de Ação e Diretrizes")
            st.markdown("Siga rigorosamente as ações abaixo para mitigação de desvios e auditoria obrigatória.")
            try: st.image("plano.jpg", use_container_width=True)
            except Exception: st.error("⚠️ Arquivo 'plano.jpg' não encontrado.")
                
            st.write("---")
            resumo_10 = ["Gestao Operacional e Qualidade", "- Foco: 5 Filiais mais ofensoras", "- Data Referencia: 25/03/2026"]
            pdf_aba10 = gerar_pdf_dinamico("Plano de Acao Logistico", resumo_10, None)
            st.download_button("📄 Baixar Relatório: Plano (PDF)", data=pdf_aba10, file_name="Plano_Acao.pdf", mime="application/pdf", key="pdf_aba10")

        elif menu_selecionado == "Tendências":
            st.subheader("📈 Análise de Tendências Temporais")
            
            # --- NOVO GRÁFICO: VISÃO CLARA DOS PIORES PERÍODOS ---
            st.markdown("### ⚖️ Comparativo Direto: Danos vs Faltas")
            fig_comparativo = plot_comparativo_temporal_tipo(df_uni)
            if fig_comparativo:
                st.plotly_chart(fig_comparativo, use_container_width=True)
            else:
                st.info("Dados insuficientes para gerar o comparativo.")
                
            st.write("---")
            
            # --- GRÁFICO ANTIGO MANTIDO (LINHA DO TEMPO POR FILIAL) ---
            st.markdown("### 🏢 Evolução por Filial")
            tipo_base = st.radio("Qual base de dados você quer analisar na linha do tempo?", ["Ambas (Geral)", "Somente Danos", "Somente Faltas"], horizontal=True)
            tipo_visao = st.radio("Selecione a periodicidade:", ["Mensal", "Semanal"], horizontal=True)
            param_tempo = 'M' if tipo_visao == "Mensal" else 'W'
            
            if tipo_base == "Somente Danos": df_plot = df_danos  
            elif tipo_base == "Somente Faltas": df_plot = df_faltas 
            else: df_plot = df_uni    
                
            if not df_plot.empty:
                fig_tempo = plot_evolucao_temporal(df_plot, periodicidade=param_tempo)
                if fig_tempo: st.plotly_chart(fig_tempo, use_container_width=True)
                else: st.warning("Não foi possível gerar o gráfico de linha do tempo com as datas atuais.")
            else:
                st.warning(f"Não há dados disponíveis para a seleção: {tipo_base}")
            
            st.divider()

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
        st.code(traceback.format_exc())
