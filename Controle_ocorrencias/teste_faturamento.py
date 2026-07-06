import os
import glob
import pandas as pd

# 1. Mapeia a pasta de Downloads exatamente como o sistema faz
pasta_downloads = r"C:\Users\adriano.montes\Downloads"
padrao_arquivo = os.path.join(pasta_downloads, "NF-e_emitidas_endereços*.xlsx")
arquivos_encontrados = glob.glob(padrao_arquivo)

print("\n" + "═"*60)
print("🔍 INVESTIGAÇÃO DE ARQUIVOS NA PASTA DOWNLOADS")
print("═"*60)

if arquivos_encontrados:
    # Ordena para achar o que o Windows diz ser o mais recente
    arquivos_encontrados.sort(key=os.path.getmtime)
    ultimo_arquivo = arquivos_encontrados[-1]
    
    print(f"📄 ARQUIVO QUE O PYTHON ESTÁ LENDO:\n   ➔ {os.path.basename(ultimo_arquivo)}")
    print(f"📅 CAMINHO COMPLETO:\n   ➔ {ultimo_arquivo}")
    print(f"🕒 ÚLTIMA MODIFICAÇÃO (Timestamp): {os.path.getmtime(ultimo_arquivo)}")
    print("═"*60)
    
    try:
        # Lê apenas as primeiras 5 linhas para não travar
        df_teste = pd.read_excel(ultimo_arquivo, nrows=5)
        
        print("📊 COLUNAS REAIS ENCONTRADAS NESTE ARQUIVO:")
        for idx, col in enumerate(df_teste.columns):
            print(f"   [{idx}] -> {col}")
            
        print("\n👀 AMOSTRA DAS 3 PRIMEIRAS LINHAS DA COLUNA [0] e [1]:")
        for i, row in df_teste.head(3).iterrows():
            print(f"   Linha {i} -> Coluna 0: {row.iloc[0]} | Coluna 1: {row.iloc[1]}")
            
    except Exception as e:
        print(f"❌ Erro ao tentar abrir o arquivo: {str(e)}")
else:
    print("⚠️ NENHUM arquivo que comece com 'NF-e_emitidas_endereços' foi encontrado em Downloads!")

print("═"*60 + "\n")