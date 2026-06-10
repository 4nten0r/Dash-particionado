import streamlit as st
import pandas as pd

def aplicar_filtros_barra_lateral(df_uni_base, df_danos_base, df_faltas_base):
    """Cria a barra lateral, captura as escolhas do usuário e filtra os DataFrames."""
    
    with st.sidebar:
        st.header("🔍 Filtros Integrados")
        
        max_itens = int(df_uni_base["Quantidade"].max()) if not df_uni_base.empty else 1000
        outlier_limite = st.slider("🚫 Ocultar registos acima de (Outliers):", 1, max_itens, max_itens)
        st.divider()
        
        # --- 1. CAIXAS DE SELEÇÃO PRIMEIRO ---
        opcoes_filial = sorted(df_uni_base["Filial"].dropna().unique())
        opcoes_motorista = sorted(df_uni_base["Motorista"].dropna().unique())
        opcoes_empresa = sorted([str(x) for x in df_uni_base["Empresa"].dropna().unique() if str(x) not in ['Não Identificado', 'N/A']])
        opcoes_canal = sorted([str(x) for x in df_uni_base["Canal"].dropna().unique() if str(x) not in ['Não Identificado', 'N/A']])
        opcoes_categoria = sorted([str(x) for x in df_uni_base["Categoria"].dropna().unique() if str(x) not in ['Não Identificado', 'nan', 'N/A', '']])

        filial_sel = st.selectbox("🏢 Filial:", options=opcoes_filial, index=None, placeholder="Todas")
        motorista_sel = st.selectbox("🚛 Motorista:", options=opcoes_motorista, index=None, placeholder="Todos")
        empresa_sel = st.selectbox("🏭 Empresa (Danos):", options=opcoes_empresa, index=None, placeholder="Todas")
        canal_sel = st.multiselect("🛍️ Marca Canal (Faltas):", options=opcoes_canal, placeholder="Escolha um ou mais...")
        categoria_sel = st.multiselect("🏷️ Categoria:", options=opcoes_categoria, placeholder="Todas as categorias...")

        st.divider()

        # --- 2. CALENDÁRIO ---
        if not df_uni_base.empty and 'Data_Filtro' in df_uni_base.columns and not df_uni_base['Data_Filtro'].dropna().empty:
            min_date = df_uni_base['Data_Filtro'].dropna().min().date()
            max_date = df_uni_base['Data_Filtro'].dropna().max().date()
            if min_date == max_date:
                min_date = min_date - pd.Timedelta(days=7)
        else:
            hoje = pd.to_datetime('today').date()
            min_date = hoje - pd.Timedelta(days=30)
            max_date = hoje

        datas_selecionadas = st.date_input(
            "📅 Período de Análise:",
            value=(min_date, max_date),
            format="DD/MM/YYYY",
            help="Selecione primeiro a data de INÍCIO e depois a data de FIM."
        )

    # --- 3. APLICANDO AS REGRAS MATEMÁTICAS ---
    
    # GARANTIA FINAL: Força a conversão das bases na hora do recorte para evitar bugs de tipo
    if 'Data_Filtro' in df_uni_base.columns: df_uni_base["Data_Filtro"] = pd.to_datetime(df_uni_base["Data_Filtro"], errors='coerce')
    if 'Data_Filtro' in df_danos_base.columns: df_danos_base["Data_Filtro"] = pd.to_datetime(df_danos_base["Data_Filtro"], errors='coerce')
    if 'Data_Filtro' in df_faltas_base.columns: df_faltas_base["Data_Filtro"] = pd.to_datetime(df_faltas_base["Data_Filtro"], errors='coerce')

    df_uni = df_uni_base[df_uni_base["Quantidade"] <= outlier_limite].copy()
    df_danos = df_danos_base[df_danos_base["Quantidade"] <= outlier_limite].copy()
    df_faltas = df_faltas_base[df_faltas_base["Quantidade"] <= outlier_limite].copy()

    # Aplica o filtro de data somente se o utilizador clicou no INÍCIO e FIM
    if isinstance(datas_selecionadas, tuple) and len(datas_selecionadas) == 2:
        start_date, end_date = datas_selecionadas
        t_start = pd.to_datetime(start_date)
        t_end = pd.to_datetime(end_date) + pd.Timedelta(hours=23, minutes=59, seconds=59)
        
        if 'Data_Filtro' in df_uni.columns: 
            df_uni = df_uni[(df_uni['Data_Filtro'] >= t_start) & (df_uni['Data_Filtro'] <= t_end)]
        if 'Data_Filtro' in df_danos.columns: 
            df_danos = df_danos[(df_danos['Data_Filtro'] >= t_start) & (df_danos['Data_Filtro'] <= t_end)]
        if 'Data_Filtro' in df_faltas.columns: 
            df_faltas = df_faltas[(df_faltas['Data_Filtro'] >= t_start) & (df_faltas['Data_Filtro'] <= t_end)]

    # Demais Filtros...
    if motorista_sel is not None:
        df_uni = df_uni[df_uni["Motorista"] == motorista_sel]
        df_danos = df_danos[df_danos["Motorista"] == motorista_sel]
        df_faltas = df_faltas[df_faltas["Motorista"] == motorista_sel]
        
    if filial_sel is not None:
        df_uni = df_uni[df_uni["Filial"] == filial_sel]
        df_danos = df_danos[df_danos["Filial"] == filial_sel]
        df_faltas = df_faltas[df_faltas["Filial"] == filial_sel]
            
    if empresa_sel is not None:
        df_uni = df_uni[df_uni["Empresa"] == empresa_sel]
        df_danos = df_danos[df_danos["Empresa"] == empresa_sel]
        df_faltas = df_faltas[df_faltas["Empresa"] == empresa_sel]
        
    if len(canal_sel) > 0:
        df_uni = df_uni[df_uni["Canal"].isin(canal_sel)]
        df_danos = df_danos[df_danos["Canal"].isin(canal_sel)]
        df_faltas = df_faltas[df_faltas["Canal"].isin(canal_sel)]

    if len(categoria_sel) > 0:
        df_uni = df_uni[df_uni["Categoria"].isin(categoria_sel)]
        df_danos = df_danos[df_danos["Categoria"].isin(categoria_sel)]
        df_faltas = df_faltas[df_faltas["Categoria"].isin(categoria_sel)]

    return df_uni, df_danos, df_faltas
