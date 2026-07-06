import sqlite3
import os
import glob

def escanear_todos_os_bancos():
    print("=" * 70)
    print("🕵️‍♂️ MÓDULO ADRIANO - RASTREADOR COMPLETO DE BANCOS DE DADOS (.DB)")
    print("=" * 70)
    
    diretorio_atual = os.getcwd()
    print(f"📁 Procurando arquivos na pasta atual:\n👉 {diretorio_atual}\n")
    
    # Busca por qualquer arquivo que termine com .db, .db3 ou .sqlite
    arquivos_encontrados = []
    for extensao in ['*.db', '*.db3', '*.sqlite', '*.sqlite3']:
        arquivos_encontrados.extend(glob.glob(extensao))
        
    if not arquivos_encontrados:
        print("❌ NENHUM arquivo de banco de dados (.db) foi localizado nesta pasta!")
        print("💡 Verifique se os arquivos não estão em uma subpasta (ex: instance/ ou database/).")
        print("=" * 70)
        return

    print(f"🎯 Sucesso! Encontrei {len(arquivos_encontrados)} arquivo(s) de banco. Iniciando varredura...\n")
    
    for arquivo in arquivos_encontrados:
        print("-" * 70)
        print(f"📦 BANCO DETECTADO: {arquivo.upper()}")
        print(f"⚖️  Tamanho: {os.path.getsize(arquivo)} bytes")
        print("-" * 70)
        
        conn = None
        try:
            conn = sqlite3.connect(arquivo)
            cursor = conn.cursor()
            
            # Listar tabelas do arquivo atual
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tabelas = cursor.fetchall()
            
            if not tabelas:
                print("   ⚠️  Arquivo existente, mas está 100% VAZIO (sem tabelas).")
                continue
                
            print(f"   📋 Tabelas encontradas neste arquivo ({len(tabelas)} no total):")
            for i, t in enumerate(tabelas, 1):
                nome_tabela = t[0]
                
                # Conta as linhas de cada tabela
                cursor.execute(f"SELECT COUNT(*) FROM [{nome_tabela}]")
                qtd_linhas = cursor.fetchone()[0]
                print(f"      {i}. [Tabela]: {nome_tabela.ljust(30)} ➡️ {qtd_linhas} linhas gravadas")
                
            print("\n   👀 Últimos lançamentos encontrados neste arquivo:")
            for t in tabelas:
                nome_tabela = t[0]
                try:
                    cursor.execute(f"SELECT * FROM [{nome_tabela}] ORDER BY rowid DESC LIMIT 2")
                    linhas = cursor.fetchall()
                    if linhas:
                        print(f"      🔹 Na tabela '{nome_tabela}':")
                        for idx, l in enumerate(linhas, 1):
                            print(f"         Lançamento {idx}: {l}")
                except:
                    pass
                    
        except Exception as e:
            print(f"   ❌ Erro ao ler este arquivo: {str(e)}")
        finally:
            if conn:
                conn.close()
                
    print("\n" + "=" * 70)
    print("🔒 Varredura geral concluída com segurança.")
    print("=" * 70)

if __name__ == "__main__":
    escanear_todos_os_bancos()