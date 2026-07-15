import pandas as pd
from datetime import datetime

# =============================================================================
# FUNÇÕES DE APOIO (O "Cérebro" do robô)
# =============================================================================
def carregar_arquivo_seguro(caminho_arquivo, pular_linhas=None, force_sep=None):
    """Tenta ler o arquivo sem dar erro de codificação. 
    Tenta primeiro com ; e depois com \t.
    """
    if force_sep:
        try:
            return pd.read_csv(caminho_arquivo, sep=force_sep, skiprows=pular_linhas, low_memory=False, encoding='utf-8')
        except UnicodeDecodeError:
            return pd.read_csv(caminho_arquivo, sep=force_sep, skiprows=pular_linhas, low_memory=False, encoding='latin1')

    # Tenta com ; primeiro (padrão antigo)
    try:
        df = pd.read_csv(caminho_arquivo, sep=';', skiprows=pular_linhas, low_memory=False, encoding='utf-8')
        if len(df.columns) > 1: return df 
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(caminho_arquivo, sep=';', skiprows=pular_linhas, low_memory=False, encoding='latin1')
            if len(df.columns) > 1: return df
        except Exception:
            pass

    # Se não funcionou ou só achou 1 coluna (tudo junto), tenta com tabulação \t
    try:
        return pd.read_csv(caminho_arquivo, sep='\t', skiprows=pular_linhas, low_memory=False, encoding='utf-8')
    except UnicodeDecodeError:
        return pd.read_csv(caminho_arquivo, sep='\t', skiprows=pular_linhas, low_memory=False, encoding='latin1')

def processa_top_motoristas(lista_motoristas, df_base, tipo_ocorrencia, linhas_finais, colunas_finais, meses_map):
    """Mapeia os dados dos ofensores para o formato da planilha de justificativas."""
    for mot in lista_motoristas:
        df_mot = df_base[df_base['Motorista'] == mot]
        if df_mot.empty: continue
        
        filial = df_mot['Filial'].mode()[0] if not df_mot['Filial'].mode().empty else ''
        rota = df_mot['Rota'].mode()[0] if not df_mot['Rota'].mode().empty else ''
        
        top_clientes = df_mot.groupby('Cliente')['Quantidade'].sum().nlargest(3).index.tolist()
        cn = " // ".join(str(c) for c in top_clientes if str(c).strip() != 'nan')
        
        # Puxa todos os pedidos únicos e junta com "//"
        pedidos_lista = df_mot['Pedido'].dropna().astype(str).unique()
        pedidos_lista = [p for p in pedidos_lista if p.strip() and p.upper() != 'NAN']
        str_pedidos = " // ".join(pedidos_lista)
        
        ocorrencias_mes = df_mot.groupby('Mes')['Quantidade'].sum().to_dict()
        
        descricoes = df_mot['Descricao'].dropna().astype(str).unique()
        descricoes = [d for d in descricoes if len(d.strip()) > 5][:2]
        desc_final = "\n\n".join(descricoes)
        
        linha = {col: '' for col in colunas_finais}
        linha['MOTORISTA'] = f"{mot}" 
        linha['CN'] = cn
        linha['PEDIDOS'] = str_pedidos
        linha['FILIAL'] = filial
        linha['ROTA '] = rota
        
        for num_mes, nome_mes in meses_map.items():
            qtd = ocorrencias_mes.get(num_mes, 0)
            linha[nome_mes] = int(qtd) if qtd > 0 else ''
            
        linha['DESCRIÇÃO'] = desc_final
        linhas_finais.append(linha)


# =============================================================================
# PARTE 1: ROBÔ DE LIMPEZA (BASE DE DANOS)
# =============================================================================
try:
    print("--- ETAPA 1: LIMPANDO A BASE DE DANOS ---")
    arquivo_base = 'base.csv'
    arquivo_notas = 'relatorionotas.csv'
    
    # Usa a função ajustada que tenta descobrir o separador correto
    df_base = carregar_arquivo_seguro(arquivo_base)
    df_notas = carregar_arquivo_seguro(arquivo_notas, pular_linhas=7)

    # Mantida a sua configuração original de colunas
    colunas_desejadas = [9, 18, 20, 26, 31, 32, 33, 36, 47, 50, 51, 75, 80, 83]
    df_base_filtrada = df_base.iloc[:, colunas_desejadas].copy()

    df_notas_filtrada = df_notas[['Pedido', 'Motorista última viagem']].copy()

    df_base_filtrada['pedido'] = df_base_filtrada['pedido'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_notas_filtrada['Pedido'] = df_notas_filtrada['Pedido'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

    print("Cruzando as informações de pedidos e motoristas...")
    df_final = pd.merge(df_base_filtrada, df_notas_filtrada, left_on='pedido', right_on='Pedido', how='left')
    df_final = df_final.drop(columns=['Pedido']).rename(columns={'Motorista última viagem': 'motorista'})

    print("Aplicando os filtros de Transportadora e Desvio Logístico...")
    df_final = df_final[df_final['transportadora'].astype(str).str.contains('DIAS', case=False, na=False)]
    df_final = df_final[df_final['desvio_logistica'].astype(str).str.strip().str.upper() == 'SIM']

    df_final.to_csv('base_pronta.csv', index=False, encoding='utf-8-sig', sep=';')
    print(f"✅ SUCESSO! 'base_pronta.csv' gerado com {len(df_final)} linhas.")

except FileNotFoundError:
    print("\nERRO NA ETAPA 1: Arquivos base.csv ou relatorionotas.csv não encontrados.")
    exit() 
except Exception as e:
    print(f"\nErro inesperado na Etapa 1: {e}")
    exit()


# =============================================================================
# PARTE 2: GERAÇÃO DA TABELA DE JUSTIFICATIVAS PARA OS RTs
# =============================================================================
try:
    print("\n--- ETAPA 2: GERANDO PLANILHAS DE JUSTIFICATIVAS SEPARADAS ---")
    
    # Aqui também usamos o carregamento seguro caso a base já venha com tab
    df_danos = carregar_arquivo_seguro("base_pronta.csv")
    
    try:
        df_faltas = carregar_arquivo_seguro("base_falta_pronta.csv")
    except FileNotFoundError:
        print("AVISO: 'base_falta_pronta.csv' não encontrada. A planilha será gerada apenas com os Danos.")
        df_faltas = pd.DataFrame() 

    # --- Padronizar Danos ---
    df_danos_std = pd.DataFrame()
    df_danos_std['Motorista'] = df_danos['motorista'].astype(str).str.strip()
    df_danos_std['Quantidade'] = pd.to_numeric(df_danos.get('qtd_reclamada', 0), errors='coerce').fillna(0)
    df_danos_std['Filial'] = df_danos.get('filial', '')
    df_danos_std['Rota'] = df_danos.get('id_rota', '')
    df_danos_std['Cliente'] = df_danos.get('cliente', '')
    df_danos_std['Pedido'] = df_danos.get('pedido', '')
    
    # Busca da data completa com conversão flexível (format='mixed')
    if 'data_ref' in df_danos.columns:
        df_danos_std['Data'] = pd.to_datetime(df_danos['data_ref'], dayfirst=True, format='mixed', errors='coerce')
    elif len(df_danos.columns) > 0:
        df_danos_std['Data'] = pd.to_datetime(df_danos.iloc[:, 0], dayfirst=True, format='mixed', errors='coerce')
    else:
        df_danos_std['Data'] = pd.NaT
        
    df_danos_std['Mes'] = df_danos_std['Data'].dt.month.fillna(0)
    df_danos_std['Descricao'] = df_danos.get('descricao_ocorrencia', '')

    # --- Padronizar Faltas ---
    df_faltas_std = pd.DataFrame()
    if not df_faltas.empty:
        # Pega a primeira coluna como 'Motorista' se o nome padrão não existir
        col_mot = 'Motorista ultima viagem' if 'Motorista ultima viagem' in df_faltas.columns else df_faltas.columns[0]
        df_faltas_std['Motorista'] = df_faltas.get(col_mot, '').astype(str).str.strip()
        
        df_faltas_std['Quantidade'] = pd.to_numeric(df_faltas.get('cantidad_itens', 0), errors='coerce').fillna(0)
        df_faltas_std['Filial'] = df_faltas.get('filial', '')
        df_faltas_std['Rota'] = df_faltas.get('rota', '')
        df_faltas_std['Cliente'] = df_faltas.get('name1', '')
        df_faltas_std['Pedido'] = df_faltas.get('nm_pedido', '')
        
        # Busca da data completa com conversão flexível (format='mixed')
        if 'mes' in df_faltas.columns:
            df_faltas_std['Data'] = pd.to_datetime(df_faltas['mes'], dayfirst=True, format='mixed', errors='coerce')
        elif len(df_faltas.columns) > 0:
            df_faltas_std['Data'] = pd.to_datetime(df_faltas.iloc[:, 0], dayfirst=True, format='mixed', errors='coerce')
        else:
            df_faltas_std['Data'] = pd.NaT
            
        df_faltas_std['Mes'] = df_faltas_std['Data'].dt.month.fillna(0)
        df_faltas_std['Descricao'] = df_faltas.get('description', '')

    # --- Limpar motoristas não identificados ---
    for val in ['NAN', 'NÃO IDENTIFICADO', 'NONE', '']:
        df_danos_std = df_danos_std[df_danos_std['Motorista'].str.upper() != val]
        if not df_faltas_std.empty:
            df_faltas_std = df_faltas_std[df_faltas_std['Motorista'].str.upper() != val]

    # =========================================================================
    # 🧠 NOVO: INTERAÇÃO DE FILTRO DINÂMICO DE PERÍODO (POR DIA)
    # =========================================================================
    print("\n" + "="*60)
    print("🎯 FILTRO DE PERÍODO PARA OS OFENSORES (TRATATIVAS)")
    print("="*60)
    data_inicio_str = input("👉 Data Inicial (ex: 01/04/2026) [ou ENTER para histórico todo]: ").strip()

    if data_inicio_str:
        data_fim_str = input("👉 Data Final (ex: 30/04/2026) [ou ENTER para assumir a data de HOJE]: ").strip()
        
        try:
            # Usando to_datetime com dayfirst=True permite aceitar tanto dd/mm/aa quanto dd/mm/aaaa
            data_inicio = pd.to_datetime(data_inicio_str, dayfirst=True)
            
            # Converte a data final (ou pega o dia de hoje)
            if data_fim_str:
                data_fim = pd.to_datetime(data_fim_str, dayfirst=True)
            else:
                data_fim = pd.to_datetime('today').normalize() # Hoje 00:00:00
                
            # Adiciona 23:59:59 no dia final para não cortar as ocorrências do último dia
            data_fim = data_fim + pd.Timedelta(hours=23, minutes=59, seconds=59)
            
            # Aplica o filtro de recorte nas bases
            df_danos_std = df_danos_std[(df_danos_std['Data'] >= data_inicio) & (df_danos_std['Data'] <= data_fim)]
            if not df_faltas_std.empty:
                df_faltas_std = df_faltas_std[(df_faltas_std['Data'] >= data_inicio) & (df_faltas_std['Data'] <= data_fim)]
                
            print(f"\n✅ Perfeito! Buscando ofensores no período de {data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}...")
        except Exception as e:
            print("\n⚠️ O formato da data parece incorreto. Puxando o histórico completo por segurança...")
    else:
        print("\n✅ Entendido! Buscando os Top 10 Ofensores de TODO o histórico...")
    print("="*60 + "\n")
    # =========================================================================

    # --- Selecionar Top 10 ---
    top_danos = df_danos_std.groupby('Motorista')['Quantidade'].sum().nlargest(10).index.tolist()
    top_faltas = df_faltas_std.groupby('Motorista')['Quantidade'].sum().nlargest(10).index.tolist() if not df_faltas_std.empty else []

    # --- Preparar a estrutura final ---
    meses_map = {1: 'JAN', 2: 'FEV', 3: 'MAR', 4: 'ABR', 5: 'MAI', 6: 'JUN', 
                 7: 'JUL', 8: 'AGO', 9: 'SET', 10: 'OUT', 11: 'NOV', 12: 'DEZ'}

    colunas_finais = ['MOTORISTA', 'CN', 'PEDIDOS', 'FILIAL', 'ROTA ', 'JAN', 'FEV', 'MAR', 'ABR', 
                      'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ', 'DESCRIÇÃO', 
                      'ANALISE', 'AÇÕES', 'AÇÃO PREVENTIVA', 'RESPONSÁVEL', 'PRAZO', 
                      'REALIZADO', 'STATUS', 'PERIODO']

    # --- LISTAS SEPARADAS PARA DANOS E FALTAS ---
    linhas_danos = []
    linhas_faltas = []

    # Processa as informações preenchendo as listas separadas
    processa_top_motoristas(top_danos, df_danos_std, "Danos", linhas_danos, colunas_finais, meses_map)
    processa_top_motoristas(top_faltas, df_faltas_std, "Faltas", linhas_faltas, colunas_finais, meses_map)

    # --- Salvar Arquivos Separados ---
    df_justificativas_danos = pd.DataFrame(linhas_danos, columns=colunas_finais)
    df_justificativas_danos.to_csv("tabela_justificativas_danos.csv", sep=";", index=False, encoding='utf-8-sig')
    print(f"✅ SUCESSO! 'tabela_justificativas_danos.csv' criada.")

    if not df_faltas_std.empty:
        df_justificativas_faltas = pd.DataFrame(linhas_faltas, columns=colunas_finais)
        df_justificativas_faltas.to_csv("tabela_justificativas_faltas.csv", sep=";", index=False, encoding='utf-8-sig')
        print(f"✅ SUCESSO! 'tabela_justificativas_faltas.csv' criada.")

except Exception as e:
    print(f"\nErro inesperado na Etapa 2: {e}")

# --- FIM DO CÓDIGO ---