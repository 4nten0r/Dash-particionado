import pandas as pd

# Colunas solicitadas da base_falta
# D=3, K=10, P=15, X=23, Y=24, AB=27, AF=31, AR=43, AW=48, AX=49
colunas_base = [4, 10, 15, 23, 24, 27, 31, 43, 48, 49]

# Carrega a planilha base_falta.csv (com encoding latin1 para evitar o erro de utf-8)
df_base = pd.read_csv('base_falta.csv', sep=';', usecols=colunas_base, encoding='latin1')

# Carrega a planilha de notas.csv
# Usamos as posições das colunas: 6 (Pedido) e 23 (Motorista)
df_notas = pd.read_csv('relatorionotas_falta.csv', sep=';', skiprows=7, usecols=[6, 23], encoding='latin1')

# Renomeia as colunas da tabela de notas para padronizar
df_notas.columns = ['Pedido', 'Motorista ultima viagem']

# Limpeza dos dados das chaves (remover espaços em branco extras e garantir formato texto)
df_base['nm_pedido'] = df_base['nm_pedido'].astype(str).str.strip()
df_notas['Pedido'] = df_notas['Pedido'].astype(str).str.strip()

# --- NOVO PASSO: Filtro de Transportadoras ---
# Limpa espaços ocultos no início e no fim dos nomes na planilha
df_base['nome_transportadora'] = df_base['nome_transportadora'].astype(str).str.strip()

# Lista com as opções exatas que você solicitou
transportadoras_permitidas = [
    "MM DELIVERY TRANSPORTES LTDA",
    "M D  DELIVERY TRANSPORTES EIRELI", # Com dois espaços, conforme solicitado
    "SAFE ADMINISTRACAO LTDA",
    "DIAS ENTREGADORA LTDA",
    "M. D. DELIVERY TRANSPORTES EIRELI",
    "M. D. DELIVERY TRANSPORTES LTDA",
    "M D DELIVERY TRANSPORTES EIRELLI",
    "M D DELIVERY TRANSPORTES EIRELI",
    "M D  DELIVERY TRANSPORTES EIRELI",
    "MD DELIVERY",
    "MD DELIVERY TRANSPORTES EIRELI",
    "MM DELIVERY"
]

# Aplica o filtro: mantém na df_base apenas as linhas onde a transportadora está na lista acima
df_base = df_base[df_base['nome_transportadora'].isin(transportadoras_permitidas)]
# ---------------------------------------------

# Remove duplicatas da tabela de notas pelo número do pedido
df_notas = df_notas.drop_duplicates(subset=['Pedido'])

# Faz o cruzamento (merge) usando o número do pedido
df_merged = pd.merge(df_base, df_notas, left_on='nm_pedido', right_on='Pedido', how='left')

# Exclui a coluna redundante de 'Pedido'
df_merged = df_merged.drop(columns=['Pedido'])

# Exporta para a nova planilha filtrada
df_merged.to_csv('base_falta_pronta.csv', sep=';', index=False, encoding='utf-8-sig')

print("Planilha 'base_falta_pronta.csv' gerada e filtrada com sucesso!")