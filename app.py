import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import traceback
import requests
from fpdf import FPDF
from io import BytesIO
import streamlit.components.v1 as components

# --- IMPORTANDO AS CAMADAS ---
from dados import load_data
from filtros import aplicar_filtros_barra_lateral
from graficos import (plot_top_motoristas, plot_comparativo_filial, plot_pizza_tipo_ocorrencia, 
                      plot_curva_abc, plot_heatmap_recorrencia, plot_mapa_rotas,
                      plot_evolucao_temporal) 

# Configuração da Página e CSS (Mantido o Redesign Visual)
st.set_page_config(page_title="Painel Integrado: Danos & Faltas", layout="wide", page_icon="🚀")
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 2.2rem; color: #2e4053; font-weight: bold; }
    [data-testid="stMetricLabel"] { font-size: 1.1rem; color: #555555; }
    div[data-testid="stBlock"] { padding-top: 1rem; padding-bottom: 1rem; }
    div.stButton > button:first-child { border-radius: 6px; border: 1px solid #4a90e2; transition: all 0.3s; }
</style>
""", unsafe_allow_html=True)

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
    
    # Cabeçalho do PDF
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, str(titulo).encode('latin-1', 'ignore').decode('latin-1'), ln=True, align="C")
    pdf.ln(5)
    
    # Linhas de Resumo/Contexto
    pdf.set_font("helvetica", "", 12)
    for linha in linhas_resumo:
        pdf.cell(0, 8, str(linha).encode('latin-1', 'ignore').decode('latin-1'), ln=True)
    pdf.ln(5)
    
    # Tabela com Top Registros da respectiva aba
    if df_tabela is not None and not df_tabela.empty:
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, "Detalhamento (Amostra dos Principais Registros)", ln=True)
        pdf.set_font("helvetica", "B", 9)
        
        # Pega as primeiras 4 colunas para caber na largura da folha A4
        colunas = list(df_tabela.columns)[:4] 
        cabecalho = " | ".join([str(c)[:18] for c in colunas])
        pdf.cell(0, 8, cabecalho.encode('latin-1', 'ignore').decode('latin-1'), ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        
        pdf.set_font("helvetica", "", 9)
        # Limita a 20 linhas para não estourar páginas desnecessariamente
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

# --- NOVAS FUNÇÕES: MOTOR DE CRUZAMENTO DE TREINAMENTOS ---
def processar_base_treinos(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

def cruzar_bases(df_danos, df_faltas, df_treinos):
    if not df_danos.empty: df_danos['Motorista'] = df_danos['Motorista'].astype(str).str.upper().str.strip()
    if not df_faltas.empty: df_faltas['Motorista'] = df_faltas['Motorista'].astype(str).str.upper().str.strip()
    if not df_treinos.empty and 'nome' in df_treinos.columns:
        df_treinos['nome'] = df_treinos['nome'].astype(str).str.upper().str.strip()

    resumo_danos = df_danos.groupby('Motorista').size().reset_index(name='Qtd_Danos') if not df_danos.empty else pd.DataFrame(columns=['Motorista', 'Qtd_Danos'])
    resumo_faltas = df_faltas.groupby('Motorista').size().reset_index(name='Qtd_Faltas') if not df_faltas.empty else pd.DataFrame(columns=['Motorista', 'Qtd_Faltas'])
    resumo_treinos = df_treinos.groupby('nome').size().reset_index(name='Qtd_Treinamentos') if not df_treinos.empty else pd.DataFrame(columns=['nome', 'Qtd_Treinamentos'])

    df_hub = pd.merge(resumo_treinos, resumo_danos, left_on='nome', right_on='Motorista', how='outer')
    df_hub['nome'] = df_hub['nome'].fillna(df_hub['Motorista']) 
    if 'Motorista' in df_hub.columns: df_hub.drop(columns=['Motorista'], inplace=True)
    
    df_hub = pd.merge(df_hub, resumo_faltas, left_on='nome', right_on='Motorista', how='outer')
    df_hub['nome'] = df_hub['nome'].fillna(df_hub['Motorista'])
    if 'Motorista' in df_hub.columns: df_hub.drop(columns=['Motorista'], inplace=True)

    df_hub['Qtd_Danos'] = df_hub['Qtd_Danos'].fillna(0).astype(int)
    df_hub['Qtd_Faltas'] = df_hub['Qtd_Faltas'].fillna(0).astype(int)
    df_hub['Qtd_Treinamentos'] = df_hub['Qtd_Treinamentos'].fillna(0).astype(int)
    return df_hub

# ==========================================
# INÍCIO DO APLICATIVO
# ==========================================
try:
    # 1. DADOS: Extração
    df_danos_base, df_faltas_base, df_uni_base, df_mapa_agg, df_coord_agg, df_trat1_base, df_trat2_base = load_data()

    # --- VACINA BLINDADA GERAL ---
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

    # 2. FILTROS: Aplicação
    df_uni, df_danos, df_faltas = aplicar_filtros_barra_lateral(df_uni_base, df_danos_base, df_faltas_base)

    # UPLOAD DE TREINAMENTOS NA BARRA LATERAL (Restaurado)
    st.sidebar.markdown("---")
    st.sidebar.header("📚 Dados de Capacitação")
    arquivo_treinamentos = st.sidebar.file_uploader("Anexe a Base de Treinamentos", type=["csv", "xlsx"])

    # 3. INTERFACE GRÁFICA GERAL
    col_titulo, col_logo = st.columns([4, 1])

    with col_titulo:
        st.markdown("""
        <h1 style='margin-bottom:0;'>🚀 Painel Integrado de Logística</h1>
        <p style='margin-top:0; font-size:18px; color:gray;'>
        Visão consolidada cruzando dados de <b>Danos</b>, <b>Faltas (NC)</b>, <b>Auditoria Logística</b> e <b>Treinamentos</b>.
        </p>
        """, unsafe_allow_html=True)

    with col_logo:
        try:
            st.image("logo.png", width=300)
        except Exception:
            pass

    st.divider()
    
    # NAVEGAÇÃO SUPERIOR ORIGINAL (Restaurada)
    aba1, aba2, aba3, aba4, aba5, aba6, aba7, aba8, aba9, aba10, aba11, aba12, aba13 = st.tabs([
        "🌐 Visão Geral", "📦 Só Danos", "📉 Só Faltas", "🎯 Curva ABC",
        "🔄 Recor. Motorista", "🔄 Recor. Cliente", "🛣️ Rotas/Mapa", "📝 Tratativas", "🚨 Fraudes", "📋 Plano de Ação", "📈 Tendências",
        "📚 Treinamentos", "🔍 Raio-X Motorista"
    ])
    
    with aba1:
        total_ocorrencias = len(df_uni)
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
                
                fig = px.bar(ranking, x='Quantidade', y='Motorista', orientation='h', 
                             color='Quantidade', color_continuous_scale='Viridis',
                             hover_data=['Filial'])
                fig.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
                
        with col_dir:
            st.markdown("**⚖️ Dano x Falta (Itens)**")
            if not df_uni.empty:
                pizza = df_uni.groupby('Tipo_Ocorrencia')['Quantidade'].sum().reset_index()
                fig_p = px.pie(pizza, names='Tipo_Ocorrencia', values='Quantidade', hole=0.4, color_discrete_map={'Dano':'#1f77b4', 'Falta':'#d62728'})
                st.plotly_chart(fig_p, use_container_width=True)

        st.write("---")
        st.markdown("**🏷️ Top 10 Categorias Afetadas (Geral)**")
        if not df_uni.empty and 'Categoria' in df_uni.columns:
            cat_ranking = df_uni.groupby('Categoria')['Quantidade'].sum().nlargest(10).reset_index()
            fig_cat1 = px.bar(cat_ranking, x='Quantidade', y='Categoria', orientation='h', 
                              color='Quantidade', color_continuous_scale='Viridis', text_auto='.0f')
            fig_cat1.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
            st.plotly_chart(fig_cat1, use_container_width=True)

        st.write("---")
        with st.expander("🔎 Ferramenta de Investigação: Explorar Dados Detalhados (Drill Down)"):
            if not df_uni.empty: st.dataframe(organizar_tabela(df_uni), use_container_width=True)
            else: st.info("Nenhum dado encontrado para os filtros atuais.")
                
        st.write("---")
        top_geral = df_uni.groupby('Motorista')['Quantidade'].sum().nlargest(15).reset_index() if not df_uni.empty else None
        resumo_1 = [f"Total Geral: {total_ocorrencias} ocorrencias", f"Danos: {len(df_danos)}", f"Faltas: {len(df_faltas)}"]
        pdf_aba1 = gerar_pdf_dinamico("Relatorio - Visao Geral", resumo_1, top_geral)
        st.download_button("📄 Baixar Relatório: Visão Geral (PDF)", data=pdf_aba1, file_name="Visao_Geral.pdf", mime="application/pdf", key="pdf_aba1")

    with aba2:
        if not df_danos.empty:
            total_itens_dano = df_danos['Quantidade'].sum()
            total_ocorrencias_dano = len(df_danos)
            media_dano = total_itens_dano / total_ocorrencias_dano
            
            c1, c2, c3 = st.columns(3)
            c1.metric("📦 Volume de Itens Danificados", f"{total_itens_dano:,.0f}", "Soma de Itens")
            c2.metric("📝 Total de Registros (NC)", total_ocorrencias_dano, "Linhas na Base", delta_color="off")
            c3.metric("⚖️ Média Itens/Ocorrência", f"{media_dano:.1f}", "Itens por NC", delta_color="off")
            
            st.write("---")

            st.markdown("### 📊 Análise de Danos: Top Motoristas e Filial")
            fig_m = plot_top_motoristas(df_danos, 'Blues')
            if fig_m: st.plotly_chart(fig_m, use_container_width=True)
            
            st.write("---")
            
            fig_f = plot_comparativo_filial(df_danos, 'Blues')
            if fig_f: st.plotly_chart(fig_f, use_container_width=True)
            
            st.write("---")
            st.markdown("### 🏷️ Categorias com Mais Danos")
            if 'Categoria' in df_danos.columns:
                cat_danos = df_danos.groupby('Categoria')['Quantidade'].sum().nlargest(10).reset_index()
                fig_cat2 = px.bar(cat_danos, x='Quantidade', y='Categoria', orientation='h', 
                                  color='Quantidade', color_continuous_scale='Blues', text_auto='.0f')
                fig_cat2.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
                st.plotly_chart(fig_cat2, use_container_width=True)
        
        st.markdown("### 📋 Tabela Organizada - Danos")
        if not df_danos.empty:
            df_tabela_formatada = organizar_tabela(df_danos)
            colunas_exibicao = [c for c in ["Motorista", "Filial", "Quantidade", "descricao_ocorrencia", "Cliente", "Pedido", "Tipo_Ocorrencia"] if c in df_tabela_formatada.columns]
            df_exibicao = df_tabela_formatada[colunas_exibicao + [c for c in df_tabela_formatada.columns if c not in colunas_exibicao]]
            st.dataframe(df_exibicao, use_container_width=True)
        else:
            st.info("Nenhum dado de dano encontrado para os filtros atuais.")
            
        st.write("---")
        top_danos = df_danos.groupby('Motorista')['Quantidade'].sum().nlargest(15).reset_index() if not df_danos.empty else None
        resumo_2 = [f"Ocorrencias Exclusivas de Dano: {len(df_danos)} registros vinculados."]
        pdf_aba2 = gerar_pdf_dinamico("Relatorio - Somente Danos", resumo_2, top_danos)
        st.download_button("📄 Baixar Relatório: Danos (PDF)", data=pdf_aba2, file_name="Relatorio_Danos.pdf", mime="application/pdf", key="pdf_aba2")

    with aba3:
        if not df_faltas.empty:
            total_itens_falta = df_faltas['Quantidade'].sum()
            total_ocorrencias_falta = len(df_faltas)
            media_falta = total_itens_falta / total_ocorrencias_falta
            
            c1, c2, c3 = st.columns(3)
            c1.metric("📦 Volume de Itens Faltantes", f"{total_itens_falta:,.0f}", "Soma de Itens")
            c2.metric("📝 Total de Registros (NC)", total_ocorrencias_falta, "Linhas na Base", delta_color="off")
            c3.metric("⚖️ Média Itens/Ocorrência", f"{media_falta:.1f}", "Itens por NC", delta_color="off")
            
            st.write("---")

            st.markdown("### 📊 Top 10 Motoristas (Volume de Itens Faltantes)")
            df_mot_falta = df_faltas.groupby('Motorista')['Quantidade'].sum().nlargest(10).reset_index()
            filial_map = df_faltas.groupby("Motorista")["Filial"].agg(lambda x: x.value_counts().index[0] if not x.empty else "Não Identificado").to_dict()
            df_mot_falta["Filial"] = df_mot_falta["Motorista"].map(filial_map)
            
            fig_m = px.bar(df_mot_falta, x='Quantidade', y='Motorista', orientation='h', color='Quantidade', color_continuous_scale='Reds', text_auto='.0f', hover_data=['Filial'])
            fig_m.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
            st.plotly_chart(fig_m, use_container_width=True)
            
            st.write("---")

            st.markdown("### 🏢 Volume de Faltas por Filial")
            df_fil_falta = df_faltas.groupby('Filial')['Quantidade'].sum().sort_values(ascending=False).reset_index()
            fig_f = px.bar(df_fil_falta, x='Filial', y='Quantidade', color='Quantidade', color_continuous_scale='Reds', text_auto='.0f')
            st.plotly_chart(fig_f, use_container_width=True)
            
            st.write("---")

            st.markdown("### 🏷️ Categorias com Maior Perda Física")
            if 'Categoria' in df_faltas.columns:
                cat_faltas = df_faltas.groupby('Categoria')['Quantidade'].sum().nlargest(10).reset_index()
                fig_cat3 = px.bar(cat_faltas, x='Quantidade', y='Categoria', orientation='h', color='Quantidade', color_continuous_scale='Reds', text_auto='.0f')
                fig_cat3.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
                st.plotly_chart(fig_cat3, use_container_width=True)
        
        st.markdown("### 📋 Tabela Organizada - Faltas")
        if not df_faltas.empty:
            df_tabela_formatada = organizar_tabela(df_faltas)
            colunas_exibicao = [c for c in ["Motorista", "Filial", "Quantidade", "descricao_ocorrencia", "Cliente", "Pedido", "Tipo_Ocorrencia"] if c in df_tabela_formatada.columns]
            df_exibicao = df_tabela_formatada[colunas_exibicao + [c for c in df_tabela_formatada.columns if c not in colunas_exibicao]]
            st.dataframe(df_exibicao, use_container_width=True)
        else:
            st.info("Nenhum dado de falta encontrado.")

    with aba4:
        st.subheader("🎯 Classificação ABC por Motorista (Reativa)")
        fig_abc, df_abc = plot_curva_abc(df_uni)
        if fig_abc:
            st.plotly_chart(fig_abc, use_container_width=True)
            st.dataframe(df_abc, use_container_width=True)
        else: st.info("Aguardando dados filtrados para calcular a Curva ABC.")
        
        st.write("---")
        resumo_4 = ["Classificacao de ofensores pelo metodo ABC (Filtro aplicado na lateral)."]
        pdf_aba4 = gerar_pdf_dinamico("Relatorio - Curva ABC", resumo_4, df_abc)
        st.download_button("📄 Baixar Relatório: Curva ABC (PDF)", data=pdf_aba4, file_name="Curva_ABC.pdf", mime="application/pdf", key="pdf_aba4")

    with aba5:
        st.subheader("🔄 Histórico Mensal de Ofensores (Motoristas)")
        fig_heat_m, df_recor_m = plot_heatmap_recorrencia(df_uni, 'Motorista')
        if fig_heat_m:
            st.plotly_chart(fig_heat_m, use_container_width=True)
            st.markdown("**📋 Motoristas Reincidentes:**")
            st.dataframe(df_recor_m, use_container_width=True)
        else: st.info("Ajuste os filtros para visualizar a recorrência.")
        
        st.write("---")
        resumo_5 = ["Acompanhamento dos Motoristas com maior reincidencia nos ultimos meses."]
        pdf_aba5 = gerar_pdf_dinamico("Recorrencia - Motoristas", resumo_5, df_recor_m)
        st.download_button("📄 Baixar Relatório: Recor. Motorista (PDF)", data=pdf_aba5, file_name="Recorrencia_Motoristas.pdf", mime="application/pdf", key="pdf_aba5")

    with aba6:
        st.subheader("🔄 Histórico Mensal de Clientes Reincidentes")
        fig_heat_c, df_recor_c = plot_heatmap_recorrencia(df_uni, 'Cliente')
        if fig_heat_c: st.plotly_chart(fig_heat_c, use_container_width=True)
        else: st.info("Nenhum cliente válido para análise na seleção atual.")
        
        st.write("---")
        resumo_6 = ["Acompanhamento dos Clientes com maior volume de ocorrencias reincidentes."]
        pdf_aba6 = gerar_pdf_dinamico("Recorrencia - Clientes", resumo_6, df_recor_c if fig_heat_c else None)
        st.download_button("📄 Baixar Relatório: Recor. Cliente (PDF)", data=pdf_aba6, file_name="Recorrencia_Clientes.pdf", mime="application/pdf", key="pdf_aba6")

    with aba7:
        st.subheader("📍 Detalhamento e Inteligência por Rota")
        
        coluna_rota_real = None
        for col in df_uni.columns:
            if col.lower() == 'rota':
                coluna_rota_real = col
                break
                
        if coluna_rota_real:
            # ==========================================
            # 1. TABELA DE OFENSORES POR ROTA
            # ==========================================
            if not df_danos.empty and coluna_rota_real in df_danos.columns:
                df_danos_rota = df_danos.groupby(coluna_rota_real)['Quantidade'].sum().reset_index(name='Qtd_Danos')
            else:
                df_danos_rota = pd.DataFrame(columns=[coluna_rota_real, 'Qtd_Danos'])
                
            if not df_faltas.empty and coluna_rota_real in df_faltas.columns:
                df_faltas_rota = df_faltas.groupby(coluna_rota_real)['Quantidade'].sum().reset_index(name='Qtd_Faltas')
            else:
                df_faltas_rota = pd.DataFrame(columns=[coluna_rota_real, 'Qtd_Faltas'])
                
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

            # ==========================================
            # 2. INVESTIGAÇÃO TEMPORAL AVANÇADA
            # ==========================================
            st.write("---")
            st.markdown("### 📈 Investigação Temporal (Rotas)")
            
            lista_rotas = df_exibicao['Rota'].unique().tolist()
            
            if lista_rotas:
                df_uni_temp = df_uni.copy()
                df_uni_temp['rota_padrao'] = df_uni_temp[coluna_rota_real].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                
                periodos_disponiveis = []
                if 'Periodo' in df_uni_temp.columns:
                    periodos_disponiveis = sorted(df_uni_temp['Periodo'].dropna().unique().tolist())
                
                col_filtro_rota, col_filtro_periodo = st.columns(2)
                
                with col_filtro_rota:
                    rotas_selecionadas = st.multiselect("1️⃣ Selecione as rotas para análise:", options=lista_rotas, default=[lista_rotas[0]] if lista_rotas else [])
                with col_filtro_periodo:
                    periodos_selecionados = st.multiselect("2️⃣ Filtre os períodos (Meses/Semanas):", options=periodos_disponiveis, default=periodos_disponiveis)
                
                if rotas_selecionadas and periodos_selecionados:
                    df_rota_hist = df_uni_temp[
                        (df_uni_temp['rota_padrao'].isin([str(r) for r in rotas_selecionadas])) & 
                        (df_uni_temp['Periodo'].isin(periodos_selecionados))
                    ]
                    
                    if not df_rota_hist.empty:
                        df_hist_grp = df_rota_hist.groupby(['Periodo', 'Tipo_Ocorrencia'])['Quantidade'].sum().reset_index()
                        df_hist_grp = df_hist_grp.sort_values(by='Periodo')
                        
                        df_total = df_rota_hist.groupby('Periodo')['Quantidade'].sum().reset_index()
                        df_total = df_total.sort_values(by='Periodo')
                        
                        if len(df_total) > 1:
                            total_inicio = df_total['Quantidade'].iloc[0]
                            total_fim = df_total['Quantidade'].iloc[-1]
                            variacao = ((total_fim - total_inicio) / max(total_inicio, 1)) * 100
                            
                            if variacao > 20: st.error(f"🚨 As rotas selecionadas apresentaram piora conjunta de {variacao:.1f}% no período.")
                            elif variacao < -20: st.success(f"✅ As rotas selecionadas apresentaram melhoria conjunta de {abs(variacao):.1f}% no período.")
                            else: st.warning("⚠️ As rotas selecionadas apresentam estabilidade operacional.")
                                
                            df_total['Variacao_%'] = (df_total['Quantidade'].pct_change() * 100).round(1).fillna(0)
                        else:
                            st.info("📊 Seleção possui ocorrências em apenas um período. Histórico insuficiente para variação.")

                        titulo_grafico = "Evolução Agregada" if len(rotas_selecionadas) > 1 else f"Evolução - Rota {rotas_selecionadas[0]}"
                        fig_hist = px.bar(
                            df_hist_grp, x='Periodo', y='Quantidade', color='Tipo_Ocorrencia', barmode='group',
                            color_discrete_map={'Dano':'#1f77b4', 'Falta':'#d62728'}, text_auto='.0f', title=titulo_grafico
                        )
                        fig_hist.update_layout(xaxis_title="Período", yaxis_title="Volume de Itens", legend_title="Tipo")
                        st.plotly_chart(fig_hist, use_container_width=True)
                        
                        if len(df_total) > 1:
                            with st.expander("Ver detalhamento do crescimento agregado período a período"):
                                st.dataframe(df_total.style.format({'Variacao_%': '{:.1f}%'}), use_container_width=True)
                    else:
                        st.info("Nenhuma ocorrência encontrada para a combinação de rotas e períodos selecionados.")
                else:
                    st.warning("⚠️ Selecione pelo menos uma rota e um período para visualizar a análise.")

            # ==========================================
            # 3. INTELIGÊNCIA GEOGRÁFICA REGIONAL
            # ==========================================
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

                # RANKINGS: Cidades e Bairros
                col_cid, col_bai = st.columns(2)
                with col_cid:
                    st.markdown("#### 🏆 Top 10 Cidades Críticas")
                    top_cidades = df_geo.groupby('Cidade')['Quantidade'].sum().nlargest(10).reset_index()
                    fig_cid = px.bar(top_cidades, x='Quantidade', y='Cidade', orientation='h', color='Quantidade', color_continuous_scale='Oranges', text_auto='.0f')
                    fig_cid.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
                    st.plotly_chart(fig_cid, use_container_width=True)

                with col_bai:
                    st.markdown("#### 🚨 Top 10 Bairros Críticos")
                    df_bairros = df_geo[df_geo['Bairro'] != 'Não Identificado']
                    top_bairros = df_bairros.groupby('Bairro')['Quantidade'].sum().nlargest(10).reset_index()
                    fig_bai = px.bar(top_bairros, x='Quantidade', y='Bairro', orientation='h', color='Quantidade', color_continuous_scale='Reds', text_auto='.0f')
                    fig_bai.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
                    st.plotly_chart(fig_bai, use_container_width=True)

                st.write("---")

                # SUNBURST: Raio-X
                st.markdown("#### 🎯 Raio-X Geográfico (Sunburst)")
                st.markdown("*Clique no centro para expandir as cidades, bairros e descobrir as rotas ofensoras de cada região.*")
                
                df_sun = df_geo.groupby(['Cidade', 'Bairro', 'rota_padrao'])['Quantidade'].sum().reset_index()
                df_sun = df_sun[df_sun['Quantidade'] > 0]
                
                fig_sun = px.sunburst(
                    df_sun, path=['Cidade', 'Bairro', 'rota_padrao'], values='Quantidade',
                    color='Quantidade', color_continuous_scale='Inferno'
                )
                fig_sun.update_layout(margin=dict(t=0, l=0, r=0, b=0), height=500)
                st.plotly_chart(fig_sun, use_container_width=True)

                st.write("---")

                # HEATMAP E EVOLUÇÃO (CIDADES)
                if 'Periodo' in df_geo.columns:
                    col_evol, col_heat = st.columns(2)
                    
                    with col_evol:
                        st.markdown("#### 📅 Evolução (Top 5 Cidades)")
                        top_5_cids = top_cidades.head(5)['Cidade'].tolist()
                        df_evol_reg = df_geo[df_geo['Cidade'].isin(top_5_cids)]
                        
                        df_evol_grp = df_evol_reg.groupby(['Periodo', 'Cidade'])['Quantidade'].sum().reset_index()
                        df_evol_grp = df_evol_grp.sort_values(by='Periodo')
                        
                        fig_evol = px.line(df_evol_grp, x='Periodo', y='Quantidade', color='Cidade', markers=True)
                        
                        fig_evol.update_layout(legend=dict(orientation="h", y=-0.2, yanchor="top", xanchor="center", x=0.5))
                        
                        st.plotly_chart(fig_evol, use_container_width=True)

                    with col_heat:
                        st.markdown("#### 🔥 Mapa de Calor Regional")
                        pivot_cid = df_geo.pivot_table(index='Cidade', columns='Periodo', values='Quantidade', aggfunc='sum', fill_value=0)
                        
                        if not pivot_cid.empty:
                            fig_heat_cid = px.imshow(pivot_cid, text_auto=True, aspect="auto", color_continuous_scale="Reds")
                            st.plotly_chart(fig_heat_cid, use_container_width=True)

            else:
                st.warning("⚠️ Para visualizar a inteligência geográfica, as informações do arquivo 'relatorionotas.csv' precisam estar carregadas corretamente.")

            # ==========================================
            # 4. EXPORTAÇÃO DE RELATÓRIO
            # ==========================================
            st.write("---")
            resumo_7 = ["Relatorio executivo contendo o detalhamento do volume de itens perdidos e danificados por rota, consolidado com inteligencia de mapa de cidades e bairros ofensores."]
            pdf_aba7 = gerar_pdf_dinamico("Dossie Geografico e Rotas", resumo_7, df_exibicao)
            st.download_button("📄 Baixar Relatório: Rotas (PDF)", data=pdf_aba7, file_name="Relatorio_Rotas_Geo.pdf", mime="application/pdf", key="pdf_aba7")
            
        else:
            st.error("Aviso: A coluna de rotas não foi encontrada na base de dados principal.")
    
    with aba8:
        st.subheader("📝 Controle de Tratativas")
        link_consolidado = "https://diaslog-my.sharepoint.com/:x:/g/personal/icaro_nascimento_mmdeliverytransportes_com_br/IQAj93IdOFz8R7FzGtY6CH7rAfzodfY-wPpnPjciYx6gHis?download=1"

        st.markdown("### 📦 Tratativas - Danos")
        df_exibicao_danos = None
        
        try:
            with st.spinner("Sincronizando Danos com o OneDrive..."):
                df_tratativas_danos = carregar_excel_nuvem_turbinado(link_consolidado, "danos").dropna(how='all').head(5).reset_index(drop=True)
            st.success("✅ Tratativas de Danos conectadas com sucesso!")
            
            with st.expander("⚙️ Escolher colunas para exibir (Danos)"):
                todas_colunas_danos = df_tratativas_danos.columns.tolist()
                colunas_selecionadas_danos = st.multiselect("Selecione as colunas desejadas:", options=todas_colunas_danos, default=todas_colunas_danos, key="multi_danos")
            
            df_exibicao_danos = df_tratativas_danos[colunas_selecionadas_danos]
            st.dataframe(df_exibicao_danos, use_container_width=True)
            
        except Exception as e:
            st.warning("⏳ Falha ao carregar a nuvem. Aguardando a verificação do link público.")
            st.info(f"Detalhe técnico: {e}")

        st.write("---") 

        st.markdown("### 🛍️ Tratativas - Faltas")
        df_exibicao_faltas = None
        
        try:
            with st.spinner("Sincronizando Faltas com o OneDrive..."):
                df_tratativas_faltas = carregar_excel_nuvem_turbinado(link_consolidado, "faltas").dropna(how='all').head(5).reset_index(drop=True)
            st.success("✅ Tratativas de Faltas conectadas direto da nuvem!")
            
            with st.expander("⚙️ Escolher colunas para exibir (Faltas)"):
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

    with aba9:
        st.subheader("🚨 Dossiê de Fraudes")
        alertas = pd.DataFrame()
        
        if not df_uni.empty:
            df_cli = df_uni[~df_uni['Cliente'].str.upper().isin(['NÃO IDENTIFICADO', 'NAN', ''])].copy()
            
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
                    f_isento['Motivo'] = 'Isento: Erro de Origem / Falta'

            f_vol = df_cli[df_cli['Quantidade'] >= 50].copy()
            f_vol['Motivo'] = 'Volume Crítico'
            
            df_rep = df_cli[df_cli['Quantidade'] >= 10].copy()
            cli_susp = df_rep.groupby(['Cliente', 'Quantidade']).size().reset_index(name='V')
            cli_susp = cli_susp[cli_susp['V'] > 1]
            f_rep = pd.merge(df_cli, cli_susp[['Cliente', 'Quantidade']], on=['Cliente', 'Quantidade'])
            f_rep['Motivo'] = 'Reclamação Idêntica'
            
            mot_suspeitos = df_cli.groupby('Motorista')['Cliente'].nunique().reset_index(name='Qtd_Clientes')
            lista_mot = mot_suspeitos[mot_suspeitos['Qtd_Clientes'] > 20]['Motorista']
            f_mot = df_cli[df_cli['Motorista'].isin(lista_mot)].copy()
            f_mot['Motivo'] = 'Motorista Risco: +20 Clientes Afetados'
            
            alertas = pd.concat([f_vol, f_rep, f_mot, f_isento])
            
            if not alertas.empty:
                alertas = alertas.drop_duplicates(subset=['Pedido', 'Motivo'])
                alertas = alertas.loc[:, ~alertas.columns.duplicated()] 
                st.error(f"⚠️ {len(alertas)} Indícios Detectados")
                
                colunas_exibicao = ['Motivo', 'Cliente', 'Pedido', 'Quantidade', 'Tipo_Ocorrencia', 'Motorista', 'Filial', 'Canal', 'description']
                colunas_existentes = [col for col in colunas_exibicao if col in alertas.columns]
                df_exibicao = alertas[colunas_existentes].copy()
                
                st.dataframe(df_exibicao, use_container_width=True)
            else: 
                st.success("✅ Tudo limpo no filtro atual.")

    with aba10:
        st.subheader("📋 Plano de Ação e Diretrizes")
        st.markdown("Siga rigorosamente as ações abaixo para mitigação de desvios e auditoria obrigatória.")
        try: st.image("plano.jpg", use_container_width=True)
        except Exception: st.error("⚠️ Arquivo 'plano.jpg' não encontrado.")
            
        st.write("---")
        resumo_10 = ["Gestao Operacional e Qualidade", "- Foco: 5 Filiais mais ofensoras", "- Data Referencia: 25/03/2026"]
        pdf_aba10 = gerar_pdf_dinamico("Plano de Acao Logistico", resumo_10, None)
        st.download_button("📄 Baixar Relatório: Plano (PDF)", data=pdf_aba10, file_name="Plano_Acao.pdf", mime="application/pdf", key="pdf_aba10")

    with aba11:
        st.subheader("📈 Análise de Tendências Temporais")
        
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

    with aba12:
        st.subheader("📚 Dashboard de Capacitação")
        if arquivo_treinamentos is None:
            st.info("👈 Por favor, anexe a base de Treinamentos (CSV/Excel) na barra lateral para visualizar os indicadores de formação.")
        else:
            df_treinos = processar_base_treinos(arquivo_treinamentos)
            if 'treinamento' in df_treinos.columns and 'filial' in df_treinos.columns:
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    cobertura = df_treinos.groupby('filial')['nome'].nunique().reset_index(name='Motoristas_Treinados')
                    fig_bar = px.bar(cobertura, x='filial', y='Motoristas_Treinados', color='Motoristas_Treinados', color_continuous_scale="Viridis", title="Cobertura por Filial")
                    st.plotly_chart(fig_bar, use_container_width=True)
                with col_t2:
                    heat = pd.pivot_table(df_treinos, index="filial", columns="treinamento", values="nome", aggfunc="count", fill_value=0)
                    fig_heat = px.imshow(heat, text_auto=True, color_continuous_scale="Viridis", title="Mapa de Calor: Tema x Filial", aspect="auto")
                    st.plotly_chart(fig_heat, use_container_width=True)
            else:
                st.warning("⚠️ O arquivo de treinamentos anexado não possui as colunas 'treinamento' e/ou 'filial'.")

    with aba13:
        st.subheader("🔍 Raio-X do Motorista: Ocorrências vs Treinamentos")
        if arquivo_treinamentos is None:
            st.info("👈 Anexe a base de Treinamentos na barra lateral para habilitar o cruzamento automático de dados de faltas, danos e treinamentos.")
        else:
            df_treinos = processar_base_treinos(arquivo_treinamentos)
            df_hub = cruzar_bases(df_danos, df_faltas, df_treinos)
            
            lista_motoristas = sorted(df_hub['nome'].unique())
            mot_selecionado = st.selectbox("Busque ou Selecione um Motorista para o Raio-X:", lista_motoristas, key="busca_mot_hub")
            
            if mot_selecionado:
                dados_mot = df_hub[df_hub['nome'] == mot_selecionado].iloc[0]
                
                c1, c2, c3 = st.columns(3)
                c1.metric("📚 Treinamentos Realizados", dados_mot['Qtd_Treinamentos'])
                c2.metric("⚠️ Ocorrências de Faltas", dados_mot['Qtd_Faltas'])
                c3.metric("📦 Ocorrências de Danos", dados_mot['Qtd_Danos'])
                
                st.markdown("<br>", unsafe_allow_html=True)
                if dados_mot['Qtd_Danos'] > 0 and dados_mot['Qtd_Treinamentos'] == 0:
                    st.error("🚨 ALERTA DE RISCO: Este motorista gerou danos/faltas no período e nunca passou por capacitação no sistema.")
                elif dados_mot['Qtd_Treinamentos'] > 0 and (dados_mot['Qtd_Danos'] + dados_mot['Qtd_Faltas']) == 0:
                    st.success("⭐ EXCELENTE: Motorista plenamente capacitado e com ocorrências zeradas.")
                else:
                    st.info("ℹ️ Perfil dentro dos limites aceitáveis. Acompanhamento normal.")

            st.write("---")
            st.markdown("#### 🏆 Visão Consolidada dos Motoristas Críticos")
            top_criticos = df_hub.sort_values(by=['Qtd_Danos', 'Qtd_Faltas'], ascending=False).head(15)
            df_melted = pd.melt(top_criticos, id_vars=['nome'], value_vars=['Qtd_Danos', 'Qtd_Faltas', 'Qtd_Treinamentos'], var_name='Indicador', value_name='Quantidade')
            df_melted['Indicador'] = df_melted['Indicador'].replace({'Qtd_Danos': 'Danos', 'Qtd_Faltas': 'Faltas', 'Qtd_Treinamentos': 'Treinos'})
            
            fig_comp = px.bar(df_melted, x='nome', y='Quantidade', color='Indicador', barmode='group', 
                              color_discrete_map={'Danos': '#d62728', 'Faltas': '#ff7f0e', 'Treinos': '#2ca02c'},
                              title="Comparativo: Top 15 Motoristas com mais Ocorrências vs. Capacitações Realizadas")
            st.plotly_chart(fig_comp, use_container_width=True)

except Exception as e:
    st.error(f"Erro no processamento: {e}")
    st.code(traceback.format_exc())
