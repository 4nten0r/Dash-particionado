import streamlit as st
import pandas as pd
import logging


def _norm_chave(serie):
    """Padroniza chaves de cruzamento (pedido/rota): texto, sem '.0' e sem espaços."""
    return serie.astype(str).str.replace(r'\.0$', '', regex=True).str.strip()


@st.cache_data(ttl=300, show_spinner="Carregando bases de dados...")
def load_data():
    mapa_meses_num = {
        1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
        7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
    }

    # ==========================================
    # 1. CARREGAR DANOS (base_pronta.csv)
    # ==========================================
    try:
        df_danos = pd.read_csv("base_pronta.csv", sep=";", encoding="latin-1")
        df_danos.columns = [str(c).replace('\ufeff', '').replace('ï»¿', '').strip().lower() for c in df_danos.columns]

        if not df_danos.empty:
            df_danos["Data_Filtro"] = pd.to_datetime(df_danos.iloc[:, 0], dayfirst=True, format='mixed', errors='coerce')
            df_danos['Periodo'] = df_danos["Data_Filtro"].dt.month.map(mapa_meses_num).fillna('Não Identificado')
        else:
            df_danos["Data_Filtro"] = pd.NaT
            df_danos['Periodo'] = 'Não Identificado'

        df_danos = df_danos.rename(columns={
            'motorista': 'Motorista', 'motorista última viagem': 'Motorista',
            'filial': 'Filial', 'id_rota': 'Rota', 'qtd_reclamada': 'Quantidade', 
            'cliente': 'Cliente', 'name1': 'Cliente',
            'pedido': 'Pedido', 'empresa': 'Empresa', 'categoria': 'Categoria'
        })
            
        df_danos['Tipo_Ocorrencia'] = 'Dano'
        df_danos['Canal'] = 'N/A'
    except Exception as e:
        logging.error(f"Erro ao carregar base de Danos: {e}")
        st.error("🚨 Erro Crítico: Não foi possível carregar o arquivo 'base_pronta.csv'. Os dados de Danos estarão vazios.")
        df_danos = pd.DataFrame()

    # ==========================================
    # 2. CARREGAR FALTAS (base_falta_pronta.csv)
    # ==========================================
    try:
        df_faltas = pd.read_csv("base_falta_pronta.csv", sep=";", encoding="latin-1")
        df_faltas.columns = [str(c).replace('\ufeff', '').replace('ï»¿', '').strip().lower() for c in df_faltas.columns]

        if not df_faltas.empty:
            df_faltas["Data_Filtro"] = pd.to_datetime(df_faltas.iloc[:, 0], dayfirst=True, format='mixed', errors='coerce')
            df_faltas['Periodo'] = df_faltas["Data_Filtro"].dt.month.map(mapa_meses_num).fillna('Não Identificado')
        else:
            df_faltas["Data_Filtro"] = pd.NaT
            df_faltas['Periodo'] = 'Não Identificado'

        df_faltas = df_faltas.rename(columns={
            'motorista ultima viagem': 'Motorista', 'motorista última viagem': 'Motorista',
            'name1': 'Cliente', 'cliente': 'Cliente', 'filial': 'Filial', 
            'rota': 'Rota', 'cantidad_itens': 'Quantidade', 
            'nm_pedido': 'Pedido', 'marca_canal': 'Canal', 'categoria': 'Categoria'
        })
            
        df_faltas['Tipo_Ocorrencia'] = 'Falta'
        df_faltas['Empresa'] = 'NATURA'
    except Exception as e:
        logging.error(f"Erro ao carregar base de Faltas: {e}")
        st.error("🚨 Erro Crítico: Não foi possível carregar o arquivo 'base_falta_pronta.csv'. Os dados de Faltas estarão vazios.")
        df_faltas = pd.DataFrame()

    # ==========================================
    # 3. UNIFICAR E BLINDAR
    # ==========================================
    colunas_comuns = ['Cliente', 'Pedido', 'Motorista', 'Filial', 'Categoria', 'Rota', 'Tipo_Ocorrencia', 'Quantidade', 'Periodo', 'Empresa', 'Canal', 'Data_Filtro']
    
    for df in [df_danos, df_faltas]:
        if not df.empty:
            if 'Quantidade' in df.columns:
                df['Quantidade'] = pd.to_numeric(df['Quantidade'], errors='coerce').fillna(0)

            for col in colunas_comuns:
                if col not in df.columns: 
                    if col == 'Data_Filtro': df[col] = pd.NaT
                    else: df[col] = 'Não Identificado'
                
                if col not in ['Data_Filtro', 'Quantidade']:
                    df[col] = df[col].fillna('Não Identificado')

    # Unifica filiais que representam a mesma unidade
    _FILIAIS_DCX = {
        'DIAS MD MEGA RIO DE JANEIRO',
        'DIAS DCX BAIXADA FLUMINENSE',
        'DIAS DUQUE DE CAXIAS MEGA FILIAL',
    }
    for df in [df_danos, df_faltas]:
        if not df.empty and 'Filial' in df.columns:
            df['Filial'] = df['Filial'].where(~df['Filial'].isin(_FILIAIS_DCX), 'DIAS DUQUE DE CAXIAS')

    df_unificado = pd.concat([df_danos[colunas_comuns], df_faltas[colunas_comuns]], ignore_index=True)
    if not df_unificado.empty and 'Rota' in df_unificado.columns:
        df_unificado['Rota'] = df_unificado['Rota'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

    # ==========================================
    # 4. CARREGAR MAPAS
    # ==========================================
    df_ped_geo = pd.DataFrame()
    try:
        df_notas = pd.read_csv("relatorionotas.csv", sep=";", encoding="latin-1", skiprows=7)
        df_falta = pd.read_csv("relatorionotas_falta.csv", sep=";", encoding="latin-1", skiprows=7)
        df_ref = pd.concat([df_notas, df_falta], ignore_index=True)

        # Mapa Pedido -> Cidade/Bairro (cruzamento confiável: 100% das ocorrencias batem por pedido,
        # ao contrario da Rota, cuja codificacao difere entre Natura e Diaslog)
        if 'Pedido' in df_ref.columns and 'Cidade' in df_ref.columns:
            df_ped_geo = df_ref[['Pedido', 'Cidade', 'Bairro']].copy()
            df_ped_geo['Pedido'] = _norm_chave(df_ped_geo['Pedido'])
            df_ped_geo = df_ped_geo[df_ped_geo['Pedido'].ne('') & df_ped_geo['Pedido'].ne('nan')]
            # 1 linha por pedido, priorizando registros com Cidade preenchida
            df_ped_geo = df_ped_geo.sort_values('Cidade', na_position='last').drop_duplicates(subset=['Pedido'], keep='first')

        if 'Rota' in df_ref.columns:
            df_geo = df_ref[['Rota', 'Cidade', 'Bairro', 'LATITUDE', 'LONGITUDE']].dropna(subset=['Rota'])
            df_geo['LATITUDE'] = pd.to_numeric(df_geo['LATITUDE'].astype(str).str.replace(',', '.'), errors='coerce')
            df_geo['LONGITUDE'] = pd.to_numeric(df_geo['LONGITUDE'].astype(str).str.replace(',', '.'), errors='coerce')
            df_geo['Rota'] = df_geo['Rota'].astype(str).str.strip()

            df_geo_agg = df_geo.groupby('Rota').agg({
                'Cidade': lambda x: x.value_counts().index[0] if not x.dropna().empty else 'N/A',
                'Bairro': lambda x: x.value_counts().index[0] if not x.dropna().empty else 'N/A',
                'LATITUDE': 'mean',
                'LONGITUDE': 'mean'
            }).reset_index()

            df_coord_agg = df_geo_agg[['Rota', 'LATITUDE', 'LONGITUDE']].copy()
            df_mapa_agg = df_geo_agg[['Rota', 'Cidade', 'Bairro']].copy()
        else:
            df_coord_agg, df_mapa_agg = pd.DataFrame(), pd.DataFrame()

    except Exception as e:
        logging.warning(f"Aviso ao carregar mapas geográficos: {e}")
        st.warning("⚠️ Os arquivos de notas ('relatorionotas.csv' ou 'relatorionotas_falta.csv') não puderam ser carregados corretamente. As abas de mapa podem estar limitadas.")
        df_coord_agg, df_mapa_agg = pd.DataFrame(), pd.DataFrame()

    # ==========================================
    # 4b. ENRIQUECER OCORRÊNCIAS COM CIDADE/BAIRRO (POR PEDIDO)
    # ==========================================
    def _enriquecer_geo(df):
        if df.empty or 'Pedido' not in df.columns:
            return df
        if df_ped_geo.empty:
            df['Cidade'] = 'Não Identificada'
            df['Bairro'] = 'Não Identificado'
            return df
        chave = _norm_chave(df['Pedido'])
        mapa_cid = dict(zip(df_ped_geo['Pedido'], df_ped_geo['Cidade']))
        mapa_bai = dict(zip(df_ped_geo['Pedido'], df_ped_geo['Bairro']))
        df['Cidade'] = chave.map(mapa_cid).fillna('Não Identificada')
        df['Bairro'] = chave.map(mapa_bai).fillna('Não Identificado')
        return df

    df_danos = _enriquecer_geo(df_danos)
    df_faltas = _enriquecer_geo(df_faltas)
    df_unificado = _enriquecer_geo(df_unificado)

    # ==========================================
    # 5. CARREGAR TRATATIVAS LOCAIS
    # ==========================================
    try:
        df_trat1 = pd.read_csv("Tratativas.csv", sep=";", encoding="latin-1").dropna(subset=['MOTORISTA'])
        df_trat2 = pd.read_csv("tratativas2.csv", sep=";", encoding="latin-1").dropna(subset=['MOTORISTA'])
    except Exception as e:
        logging.warning(f"Aviso ao carregar arquivos locais de tratativas: {e}")
        # Aqui não precisamos de st.warning na tela principal porque as tratativas agora vêm da aba 8 (Nuvem).
        df_trat1, df_trat2 = pd.DataFrame(), pd.DataFrame()

    return df_danos, df_faltas, df_unificado, df_mapa_agg, df_coord_agg, df_trat1, df_trat2
