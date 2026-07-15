import plotly.express as px
import pandas as pd
import streamlit as st
import logging

def plot_top_motoristas(df_filtrado, escala_cor):
    if df_filtrado.empty: return None
    ranking = df_filtrado.groupby('Motorista')['Quantidade'].sum().nlargest(10).reset_index()
    filial_map = df_filtrado.groupby("Motorista")["Filial"].agg(lambda x: x.value_counts().index[0] if not x.empty else "N/A").to_dict()
    ranking["Filial"] = ranking["Motorista"].map(filial_map)
    fig = px.bar(ranking, x='Quantidade', y='Motorista', orientation='h', color='Quantidade', color_continuous_scale=escala_cor, hover_data=['Filial'])
    fig.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False)
    return fig

def plot_comparativo_filial(df_filtrado, escala_cor):
    if df_filtrado.empty: return None
    contagem = df_filtrado.groupby("Filial")["Quantidade"].sum().reset_index().sort_values("Quantidade", ascending=False)
    fig = px.bar(contagem, x='Filial', y='Quantidade', text='Quantidade', color='Quantidade', color_continuous_scale=escala_cor)
    fig.update_layout(xaxis={'categoryorder':'total descending'}, showlegend=False)
    return fig

def plot_pizza_tipo_ocorrencia(df_filtrado):
    if df_filtrado.empty: return None
    pizza = df_filtrado.groupby('Tipo_Ocorrencia')['Quantidade'].sum().reset_index()
    fig = px.pie(pizza, names='Tipo_Ocorrencia', values='Quantidade', hole=0.4, color_discrete_map={'Dano':'#1f77b4', 'Falta':'#d62728'})
    return fig

def plot_curva_abc(df_filtrado):
    """Calcula a Curva ABC e retorna o gráfico e a tabela final."""
    if df_filtrado.empty: return None, None
    abc = df_filtrado.groupby('Motorista')['Quantidade'].sum().sort_values(ascending=False).reset_index()
    abc['SomaAcum'] = abc['Quantidade'].cumsum()
    abc['PercAcum'] = 100 * abc['SomaAcum'] / abc['Quantidade'].sum()
    abc['Classe'] = abc['PercAcum'].apply(lambda x: 'A (Crítico - 70%)' if x <= 70 else ('B (Atenção - 20%)' if x <= 90 else 'C (Normal - 10%)'))
    fig = px.bar(abc, x='Motorista', y='Quantidade', color='Classe', color_discrete_map={'A (Crítico - 70%)':'#d62728','B (Atenção - 20%)':'#ff7f0e','C (Normal - 10%)':'#2ca02c'})
    return fig, abc

def plot_heatmap_recorrencia(df, coluna_alvo):
    """Gera o Heatmap focado no volume de itens (quantidade). Funciona para Motorista ou Cliente!"""
    try:
        df_valido = df[~df[coluna_alvo].str.upper().isin(['NÃO IDENTIFICADO', 'NAN', ''])].copy()
        if df_valido.empty:
            return None, pd.DataFrame()

        # Opção A: inclui filial principal no rótulo do eixo Y
        if 'Filial' in df_valido.columns:
            filial_map = (
                df_valido.groupby(coluna_alvo)['Filial']
                .agg(lambda x: x.mode().iloc[0] if not x.dropna().empty else '')
                .to_dict()
            )
            df_valido['_row_label'] = (
                df_valido[coluna_alvo] + '  |  ' +
                df_valido[coluna_alvo].map(filial_map).fillna('')
            )
        else:
            df_valido['_row_label'] = df_valido[coluna_alvo]
        col_index = '_row_label'

        # Usa Ano-Mês derivado de Data_Filtro para distinguir anos diferentes
        # (evita que Set/2025 e Set/2026 apareçam na mesma coluna)
        if 'Data_Filtro' in df_valido.columns:
            datas = pd.to_datetime(df_valido['Data_Filtro'], errors='coerce')
            df_valido['_AnoMes'] = datas.dt.to_period('M')
            col_periodo = '_AnoMes'
        else:
            df_valido['_AnoMes'] = df_valido['Periodo']
            col_periodo = '_AnoMes'

        pivot = df_valido.pivot_table(
            index=col_index,
            columns=col_periodo,
            values='Quantidade',
            aggfunc='sum',
            fill_value=0
        )

        if pivot.empty:
            return None, pd.DataFrame()

        # Ordena colunas cronologicamente e formata como "Mmm/AA"
        pivot = pivot.sort_index(axis=1)
        meses_pt = {1:'Jan',2:'Fev',3:'Mar',4:'Abr',5:'Mai',6:'Jun',
                    7:'Jul',8:'Ago',9:'Set',10:'Out',11:'Nov',12:'Dez'}
        pivot.columns = [
            f"{meses_pt.get(c.month, c.month)}/{str(c.year)[2:]}"
            if hasattr(c, 'month') else str(c)
            for c in pivot.columns
        ]

        # Ordena motoristas/clientes pelos piores (maior total no topo)
        pivot['_total'] = pivot.sum(axis=1)
        pivot = pivot.sort_values(by='_total', ascending=True).drop(columns=['_total'])

        fig = px.imshow(
            pivot,
            text_auto='.0f',
            aspect="auto",
            color_continuous_scale="Reds",
            labels=dict(x="Período", y=coluna_alvo, color="Volume de Itens")
        )
        fig.update_layout(
            xaxis_title="",
            yaxis_title="",
            margin=dict(l=0, r=0, t=30, b=0)
        )

        return fig, pivot.reset_index()

    except Exception as e:
        logging.error(f"Erro ao gerar heatmap de recorrência para {coluna_alvo}: {e}")
        return None, pd.DataFrame()

def plot_mapa_rotas(df_uni, df_mapa_agg, df_coord_agg):
    """Cruza os dados geográficos e gera o mapa interativo."""
    df_rotas = df_uni[~df_uni['Rota'].str.upper().isin(['N/A', 'NAN', 'NÃO IDENTIFICADO', ''])]
    if df_rotas.empty: return None, None
    
    tabela_r = df_rotas.groupby('Rota').size().reset_index(name='Total_Geral')
    tabela_r['Rota'] = tabela_r['Rota'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    
    if not df_coord_agg.empty and 'Rota' in df_coord_agg.columns:
        df_coord_agg['Rota'] = df_coord_agg['Rota'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    else: df_coord_agg = pd.DataFrame(columns=['Rota', 'LATITUDE', 'LONGITUDE'])
        
    if not df_mapa_agg.empty and 'Rota' in df_mapa_agg.columns:
        df_mapa_agg['Rota'] = df_mapa_agg['Rota'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    else: df_mapa_agg = pd.DataFrame(columns=['Rota', 'Setor', 'Bairro'])
    
    tabela_final = pd.merge(tabela_r, df_mapa_agg, on='Rota', how='left')
    tabela_final = pd.merge(tabela_final, df_coord_agg, on='Rota', how='left')
    
    df_mapa_plot = tabela_final.dropna(subset=['LATITUDE', 'LONGITUDE'])
    
    fig = None
    if not df_mapa_plot.empty:
        fig = px.scatter_mapbox(df_mapa_plot, lat="LATITUDE", lon="LONGITUDE", size="Total_Geral", color="Total_Geral", hover_name="Setor", hover_data=["Rota", "Bairro"], zoom=7, mapbox_style="carto-positron")
    
    return fig, tabela_final[['Rota', 'Setor', 'Bairro', 'Total_Geral']].sort_values('Total_Geral', ascending=False)

def plot_mapa_cidades(df):
    """Mapa de calor agregado por CIDADE (centroide medio), dimensionado por volume de itens.
    Agrega por cidade para nao expor coordenadas de entrega individuais (LGPD)."""
    if df.empty or 'Latitude' not in df.columns or 'Cidade' not in df.columns:
        return None, 0, pd.DataFrame()

    base = df[(df['Quantidade'] > 0) & (~df['Cidade'].isin(['Não Identificada', 'Não Identificado', 'nan', '']))].copy()
    if base.empty:
        return None, 0, pd.DataFrame()

    base['Latitude'] = pd.to_numeric(base['Latitude'], errors='coerce')
    base['Longitude'] = pd.to_numeric(base['Longitude'], errors='coerce')
    sem_coord = int(base['Latitude'].isna().sum())
    base = base.dropna(subset=['Latitude', 'Longitude'])
    if base.empty:
        return None, sem_coord, pd.DataFrame()

    agg = base.groupby('Cidade').agg(
        Latitude=('Latitude', 'mean'),
        Longitude=('Longitude', 'mean'),
        Volume=('Quantidade', 'sum'),
        Ocorrencias=('Quantidade', 'size'),
    ).reset_index().sort_values('Volume', ascending=False)

    fig = px.scatter_mapbox(
        agg, lat='Latitude', lon='Longitude', size='Volume', color='Volume',
        color_continuous_scale='Reds', size_max=40, zoom=5,
        hover_name='Cidade',
        hover_data={'Volume': True, 'Ocorrencias': True, 'Latitude': False, 'Longitude': False},
        mapbox_style='carto-positron'
    )
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
    return fig, sem_coord, agg


def plot_evolucao_temporal(df, periodicidade='M'):
    if df.empty:
        return None

    df_temp = df.copy()
    col_data = 'Data_Filtro'

    df_temp[col_data] = pd.to_datetime(df_temp[col_data], errors='coerce')
    df_temp = df_temp.dropna(subset=[col_data])

    if df_temp.empty:
        return None

    if periodicidade == 'M':
        df_temp['Linha_Tempo'] = df_temp[col_data].dt.to_period('M').astype(str) 
        titulo = "Evolução Mensal de Ocorrências por Filial"
    else:
        df_temp['Linha_Tempo'] = df_temp[col_data].dt.to_period('W').astype(str)
        titulo = "Evolução Semanal de Ocorrências por Filial"
        
    df_agrupado = df_temp.groupby(['Linha_Tempo', 'Filial'])['Quantidade'].sum().reset_index()
    
    if df_agrupado.empty:
        return None
        
    fig = px.line(
        df_agrupado, x='Linha_Tempo', y='Quantidade', color='Filial', 
        markers=True, title=titulo, color_discrete_sequence=px.colors.qualitative.Set1
    )
    
    fig.update_layout(xaxis_title="Período", yaxis_title="Volume de Itens (Qtd)", hovermode="x unified", legend_title="Filial")
    return fig
    
def plot_comparativo_temporal_tipo(df):
    """Gera um gráfico de barras comparando Danos x Faltas por Ano-Mês.
    Usa Data_Filtro (Ano-Mês) em vez de 'Periodo' (nome do mês sem ano), para não
    misturar meses de anos diferentes (ex.: Set/2025 + Set/2026 na mesma barra)."""
    if df.empty or 'Data_Filtro' not in df.columns:
        return None

    dft = df.copy()
    dft['Data_Filtro'] = pd.to_datetime(dft['Data_Filtro'], errors='coerce')
    dft = dft.dropna(subset=['Data_Filtro'])
    if dft.empty:
        return None

    dft['_AnoMes'] = dft['Data_Filtro'].dt.to_period('M')
    df_grp = dft.groupby(['_AnoMes', 'Tipo_Ocorrencia'])['Quantidade'].sum().reset_index()
    df_grp = df_grp.sort_values('_AnoMes')

    # Rótulo Mmm/AA mantendo a ordem cronológica
    meses_pt = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
                7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}
    df_grp['Periodo'] = df_grp['_AnoMes'].apply(lambda p: f"{meses_pt[p.month]}/{str(p.year)[2:]}")
    ordem = list(dict.fromkeys(df_grp['Periodo']))
    df_grp['Periodo'] = pd.Categorical(df_grp['Periodo'], categories=ordem, ordered=True)
    df_grp = df_grp.sort_values('Periodo')

    # Monta o gráfico de barras agrupado (barmode='group')
    fig = px.bar(
        df_grp,
        x='Periodo',
        y='Quantidade',
        color='Tipo_Ocorrencia',
        barmode='group',
        text_auto='.0f',
        color_discrete_map={'Dano':'#1f77b4', 'Falta':'#d62728'},
        title="Volume Mensal: Danos x Faltas"
    )
    
    fig.update_layout(
        xaxis_title="", 
        yaxis_title="Volume de Itens", 
        legend_title="",
        hovermode="x unified"
    )
    
    return fig
