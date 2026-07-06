# ============================================================
# CONFIGURAÇÕES INICIAIS E DIRETÓRIOS
# ============================================================
import sys
import os

# Evita crash no Windows quando prints usam emoji/acentos no console cp1252
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import glob
import sqlite3
import threading
import base64
import calendar
from datetime import datetime, timedelta
from functools import wraps
import pandas as pd
from flask import Flask, render_template, request, redirect, send_file, jsonify, session, make_response
import webview
import socket
import re
import subprocess
from itsdangerous import URLSafeSerializer, BadSignature
import database_adapter
from modulos_portal import MODULOS_CATALOGO, listar_modulos_flat

# ============================================================
# CONFIGURAÇÕES INICIAIS E DIRETÓRIOS
# ============================================================
# ... seus imports continuam iguais para cima ...

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    TEMPLATE_DIR = os.path.join(sys._MEIPASS, 'templates')
    STATIC_DIR = os.path.join(sys._MEIPASS, 'static')
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
    STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

def registrar_log(acao, fluxo, detalhes):
    """Função temporária para o carrossel não travar até ativarmos a auditoria mestre"""
    print(f"🔹 [LOG PROVISÓRIO] {acao} | {fluxo} | {detalhes}")
    return True

# 🎯 INJEÇÃO ANTI-CACHE PARA FLASK E PYWEBVIEW
@app.after_request
def adicionar_headers_anti_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def _load_secret_key():
    """Carrega chave de sessão estável (arquivo local ou variável de ambiente)."""
    env_key = os.environ.get('FLASK_SECRET_KEY')
    if env_key:
        return env_key
    secret_file = os.path.join(BASE_DIR, '.flask_secret')
    if os.path.exists(secret_file):
        with open(secret_file, encoding='utf-8') as f:
            return f.read().strip()
    key = os.urandom(32).hex()
    with open(secret_file, 'w', encoding='utf-8') as f:
        f.write(key)
    return key


app.secret_key = _load_secret_key()
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

COOKIE_ACESSO_DIA = 'corax_acesso_dia'


def _data_hoje_str():
    return datetime.now().strftime('%Y-%m-%d')


def _segundos_ate_meia_noite():
    agora = datetime.now()
    fim = (agora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((fim - agora).total_seconds()), 60)


def _serializer_acesso_dia():
    return URLSafeSerializer(app.secret_key, salt='corax-acesso-dia-v1')


def _aplicar_sessao_usuario(usuario):
    """Grava sessão Flask do usuário autenticado."""
    session.clear()
    session.permanent = True
    session['usuario_id'] = usuario['id']
    session['usuario_nome'] = usuario['nome']
    session['usuario_login'] = usuario['login']
    session['usuario_nivel'] = str(usuario['nivel_hierarquico']).upper()


def _aplicar_sessao_do_cookie(payload):
    session.permanent = True
    session['usuario_id'] = payload['uid']
    session['usuario_nome'] = payload['nome']
    session['usuario_login'] = payload['login']
    session['usuario_nivel'] = payload['nivel']


def _ler_cookie_acesso_dia():
    token = request.cookies.get(COOKIE_ACESSO_DIA)
    if not token:
        return None
    try:
        payload = _serializer_acesso_dia().loads(token)
        if payload.get('data') != _data_hoje_str():
            return None
        if not payload.get('uid'):
            return None
        return payload
    except BadSignature:
        return None


def _anexar_cookie_acesso_dia(response, usuario):
    payload = {
        'uid': usuario['id'],
        'login': usuario['login'],
        'nome': usuario['nome'],
        'nivel': str(usuario['nivel_hierarquico']).upper(),
        'data': _data_hoje_str(),
    }
    token = _serializer_acesso_dia().dumps(payload)
    response.set_cookie(
        COOKIE_ACESSO_DIA,
        token,
        max_age=_segundos_ate_meia_noite(),
        httponly=True,
        samesite='Lax',
    )
    return response


@app.before_request
def restaurar_acesso_diario():
    """Senha só no 1º acesso do dia; demais navegações reutilizam o cookie assinado."""
    app.permanent_session_lifetime = timedelta(seconds=_segundos_ate_meia_noite())
    if 'usuario_id' in session:
        return
    payload = _ler_cookie_acesso_dia()
    if payload:
        _aplicar_sessao_do_cookie(payload)

DB_FILE = os.path.join(BASE_DIR, 'sistema_operacional.db')
database_adapter.configure(DB_FILE)
PASTA_DOWNLOADS = os.path.join(os.path.expanduser('~'), 'Downloads')
PASTA_UPLOADS_MANUAL = os.path.join(BASE_DIR, 'uploads_manuais')
ARQUIVO_FATURAMENTO_MANUAL = os.path.join(PASTA_UPLOADS_MANUAL, 'faturamento_manual.xlsx')
ARQUIVO_EXPEDICAO_MANUAL = os.path.join(PASTA_UPLOADS_MANUAL, 'expedicao_manual.xlsx')
ARQUIVO_WMS_MANUAL = os.path.join(PASTA_UPLOADS_MANUAL, 'wms_apontamento.xlsx')

EXCEL_LISTA_MOTIVOS = os.path.join(BASE_DIR, 'LISTA_MOTIVOS.xlsx')
EXCEL_OCORRENCIAS = os.path.join(BASE_DIR, 'relatorio_ocorrencias.xlsx')
EXCEL_COLETAS = os.path.join(BASE_DIR, 'relatorio_coletas.xlsx')
EXCEL_TRANSPORTADORAS = os.path.join(BASE_DIR, 'cadastro_transportadoras.xlsx')
EXCEL_CANHOTOS = os.path.join(BASE_DIR, 'relatorio_canhotos.xlsx')


def _id_str(val):
    """Normaliza ID vindo do JSON (int ou str) para string limpa."""
    return str(val or '').strip()

def sincronizar_de_para_modais():
    """
    Converte o CSV para SQLite de forma inteligente. 
    Só lê o arquivo se ele tiver sofrido alterações físicas (Ganha tempo total no boot).
    """
    if database_adapter.is_sqlserver():
        return

    caminho_csv = os.path.join(BASE_DIR, 'MODAIS.csv')
    if not os.path.exists(caminho_csv):
        print("⚠️ [AVISO LOGÍSTICO] Arquivo MODAIS.csv não localizado para conferência.")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Garante que a tabela de controle e a tabela de dados existem
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS controle_versao_csv (
                chave TEXT PRIMARY KEY,
                ultima_modificacao REAL
            )
        """)
        if database_adapter.is_sqlite():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS de_para_modais (
                    transportadora TEXT PRIMARY KEY,
                    modal_correto TEXT
                )
            """)
        
        # 2. Pega o timestamp (data/hora) real de modificação do arquivo CSV
        timestamp_atual_csv = os.path.getmtime(caminho_csv)
        
        # Verifica quando foi a última vez que gravamos isso no banco
        cursor.execute("SELECT ultima_modificacao FROM controle_versao_csv WHERE chave = 'modais_csv'")
        resultado = cursor.fetchone()
        
        # 3. MÁGICA LOGÍSTICA: Se o timestamp for idêntico, o banco já está atualizado!
        if resultado and resultado[0] == timestamp_atual_csv:
            # Conta quantas linhas já temos salvas de forma estática
            cursor.execute("SELECT COUNT(*) FROM de_para_modais")
            total_banco = cursor.fetchone()[0]
            conn.close()
            print(f"🚀 [DE-PARA OTIMIZADO] Usando tabela SQLite indexada ({total_banco} registros). Inicialização instantânea!")
            return

        # 4. Se o arquivo mudou ou é a primeira execução, faz a carga rápida
        print("🔄 [DE-PARA] Detectada alteração no MODAIS.csv. Atualizando base SQLite...")
        df_m = pd.read_csv(caminho_csv, sep=';')
        
        if not df_m.empty:
            dados_inserir = []
            for _, row in df_m.iterrows():
                transp_nome = str(row['TRANSPORTADORA']).strip().upper()
                modal_nome = str(row['DE PARA']).strip().upper()
                if transp_nome and modal_nome:
                    dados_inserir.append((transp_nome, modal_nome))
            
            # Limpa e reinsere em bloco mestre
            cursor.execute("DELETE FROM de_para_modais")
            cursor.executemany("""
                INSERT OR REPLACE INTO de_para_modais (transportadora, modal_correto) 
                VALUES (?, ?)
            """, dados_inserir)
            
            # Atualiza o timestamp de controle
            cursor.execute("""
                INSERT OR REPLACE INTO controle_versao_csv (chave, ultima_modificacao) 
                VALUES ('modais_csv', ?)
            """, (timestamp_atual_csv,))
            
            conn.commit()
            print(f"✔️ [BANCO DE DADOS] {len(dados_inserir)} transportadoras sincronizadas e indexadas no SQLite.")
            
        conn.close()
    except Exception as e:
        print(f"❌ [ERRO DE-PARA] Falha ao processar otimização: {str(e)}")

def obter_modal_transportadora(nome_transportadora):
    """Busca instantânea do modal direto na tabela SQLite indexada."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Busca por aproximação e força maiúscula para não ter erro de digitação
    cursor.execute("""
        SELECT modal_correto 
        FROM de_para_modais 
        WHERE transportadora = ?
    """, (nome_transportadora.strip().upper(),))
    
    resultado = cursor.fetchone()
    conn.close()
    
    # Se achou no banco retorna o modal, senão retorna "NÃO MAPEADO"
    return resultado[0] if resultado else "NÃO MAPEADO"

# Força a execução corrigida
sincronizar_de_para_modais()

# -------------------------------------------------------------------------
# CONEXÃO CENTRALIZADA E BLINDADA DO BANCO DE DADOS
# -------------------------------------------------------------------------
def get_db_connection():
    """Abre conexao pelo adaptador central de banco."""
    return database_adapter.get_connection()


# ============================================================
# INICIALIZAÇÃO DO BANCO DE DADOS (Executado na carga do app)
# ============================================================
def inicializar_banco():
    if database_adapter.is_sqlserver():
        print("[BANCO DE DADOS] SQL Server ativo: schema gerenciado por database/schema_sql_server.sql.")
        return

    conn = get_db_connection() # Chama nossa nova conexão blindada
    cursor = conn.cursor()
    # ... resto das tabelas continua exatamente igual

    # 📋 Tabela de Canhotos Digitais (Mobile) - Centralizada e Atualizada!
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS canhotos_digitais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            motorista TEXT NOT NULL,
            rg TEXT NOT NULL,
            transportadora TEXT NOT NULL,
            assinatura_base64 TEXT NOT NULL,
            data_hora TEXT NOT NULL,
            usuario_baixa TEXT
        )
    """)

    # 🚀 ENGENHARIA DE SEGURANÇA: Atualiza bancos já existentes adicionando a coluna de auditoria
    try:
        cursor.execute("ALTER TABLE canhotos_digitais ADD COLUMN usuario_baixa TEXT")
        print("✔️ [BANCO DE DADOS] Coluna 'usuario_baixa' integrada com sucesso à tabela.")
    except sqlite3.OperationalError:
        # Se a coluna já existir no arquivo local, o SQLite gera esse erro. 
        # Nós capturamos ele aqui para o app continuar ligando normalmente sem travar.
        pass

    # Tabela de Ocorrências
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ocorrencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT, nota_fiscal TEXT, data TEXT, tratativa TEXT, motivo TEXT
        )
    ''')

    # Tabela de Coletas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coletas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT, nota_fiscal TEXT, transportadora TEXT, data_solicitacao TEXT, status TEXT
        )
    ''')

    # Tabela de Transportadoras
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transportadoras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE, telephone TEXT, responsavel TEXT
        )
    ''')

    # Tabela de Canhotos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS canhotos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT, nota_fiscal TEXT, data_recebimento TEXT, status TEXT, observacoes TEXT
        )
    ''')

    # Tabela de Entregas Efetuadas (Módulo de Baixas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entregas_efetuadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nota_fiscal TEXT UNIQUE,
            data_entrega TEXT,
            recebedor TEXT,
            assinatura TEXT
        )
    ''')

    # Tabela de Faturamento (Cabeçalho da NF)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faturamento (
            nf TEXT PRIMARY KEY, emissao TEXT, cliente TEXT, endereco TEXT, 
            municipio TEXT, uf TEXT, cep TEXT, transportadora TEXT, 
            modalidade TEXT, volumes TEXT, especie TEXT, peso_bruto_nf TEXT, 
            pedido TEXT, valor_total_nf TEXT
        )
    """)

    # Tabela de Itens de Faturamento
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faturamento_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            nf TEXT, codigo_item TEXT, descricao_item TEXT, 
            qtde TEXT, um TEXT, peso_unitario TEXT, peso_total TEXT,
            FOREIGN KEY (nf) REFERENCES faturamento(nf)
        )
    """)

    # 💾 TABELA DE METAS DIÁRIAS (Inserida estrategicamente aqui no motor inicial)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metas_diarias (
            data TEXT PRIMARY KEY,
            valor_meta REAL
        )
    """)

    # ⚡ 4. MÓDULO DE DEVOLUÇÕES (Garante a criação da tabela de histórico multilinha)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devolucoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nota_fiscal TEXT NOT NULL,
            data_devolucao TEXT NOT NULL,
            transportadora TEXT,
            ocorrencia TEXT NOT NULL,
            cte_devolucao TEXT,
            responsavel_recebimento TEXT,
            detalhes_livre TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custos_tipos_despesa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custos_origens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custos_pessoas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custos_lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_parcelamento TEXT,
            tipo_movimento TEXT NOT NULL,
            descricao TEXT NOT NULL,
            tipo_despesa_id INTEGER,
            origem_id INTEGER,
            pessoa_id INTEGER,
            valor REAL NOT NULL,
            valor_total REAL NOT NULL,
            data_lancamento TEXT NOT NULL,
            data_prevista_pagamento TEXT,
            parcela_numero INTEGER DEFAULT 1,
            parcelas_total INTEGER DEFAULT 1,
            observacao TEXT,
            status TEXT DEFAULT 'previsto',
            criado_em TEXT NOT NULL,
            FOREIGN KEY (tipo_despesa_id) REFERENCES custos_tipos_despesa(id),
            FOREIGN KEY (origem_id) REFERENCES custos_origens(id),
            FOREIGN KEY (pessoa_id) REFERENCES custos_pessoas(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS custos_agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo_movimento TEXT NOT NULL,
            descricao TEXT NOT NULL,
            tipo_despesa_id INTEGER,
            origem_id INTEGER,
            pessoa_id INTEGER,
            valor_total REAL NOT NULL,
            dia_vencimento INTEGER NOT NULL,
            data_inicio TEXT NOT NULL,
            parcelas_total INTEGER DEFAULT 1,
            observacao TEXT,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (tipo_despesa_id) REFERENCES custos_tipos_despesa(id),
            FOREIGN KEY (origem_id) REFERENCES custos_origens(id),
            FOREIGN KEY (pessoa_id) REFERENCES custos_pessoas(id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_custos_lanc_data ON custos_lancamentos(data_prevista_pagamento);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_custos_lanc_tipo ON custos_lancamentos(tipo_despesa_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_custos_lanc_pessoa ON custos_lancamentos(pessoa_id);")

    # Migração estrutural de segurança para o módulo de canhotos do WhatsApp
    try:
        cursor.execute("ALTER TABLE canhotos_digitais ADD COLUMN nota_fiscal TEXT")
    except sqlite3.OperationalError:
        pass

    # Índices de Alta Performance
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_nf_unique ON entregas_efetuadas(nota_fiscal);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_faturamento_cliente ON faturamento(cliente);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_faturamento_transportadora ON faturamento(transportadora);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_faturamento_emissao ON faturamento(emissao);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_nf ON faturamento_itens(nf);")

    # Migração e colunas dinâmicas para o Módulo Mobile
    cursor.execute("PRAGMA table_info(entregas_efetuadas)")
    cols_entregas = [c[1] for c in cursor.fetchall()]
    if "recebedor" not in cols_entregas:
        cursor.execute("ALTER TABLE entregas_efetuadas ADD COLUMN recebedor TEXT")
    if "assinatura" not in cols_entregas:
        cursor.execute("ALTER TABLE entregas_efetuadas ADD COLUMN assinatura TEXT")

    # Colunas extras para o módulo Central Coletas FOB (tabela coletas)
    colunas_coletas_fob = [
        ("tratativa", "TEXT"),
        ("motivo", "TEXT"),
        ("prazo_coleta", "TEXT"),
        ("transp_coleta", "TEXT"),
        ("contato_celular", "TEXT"),
        ("contato_email", "TEXT"),
        ("tipo_registro", "TEXT"),
    ]
    cursor.execute("PRAGMA table_info(coletas)")
    cols_coletas = {c[1] for c in cursor.fetchall()}
    for col, tipo in colunas_coletas_fob:
        if col not in cols_coletas:
            try:
                cursor.execute(f"ALTER TABLE coletas ADD COLUMN {col} {tipo}")
            except sqlite3.OperationalError:
                pass

    # Migração única: registros FOB que estavam na tabela ocorrencias
    cursor.execute("PRAGMA table_info(ocorrencias)")
    cols_oc = {c[1] for c in cursor.fetchall()}
    if 'transp_coleta' in cols_oc:
        try:
            cursor.execute("""
                INSERT INTO coletas (
                    cliente, nota_fiscal, transportadora, data_solicitacao, status,
                    tratativa, motivo, prazo_coleta, transp_coleta, contato_celular, contato_email, tipo_registro
                )
                SELECT o.cliente, o.nota_fiscal, COALESCE(o.transp_coleta, ''), o.data, 'FOB',
                       o.tratativa, o.motivo, o.prazo_coleta, o.transp_coleta, o.contato_celular, o.contato_email, 'fob'
                FROM ocorrencias o
                WHERE (o.transp_coleta IS NOT NULL AND o.transp_coleta != '')
                   OR (o.prazo_coleta IS NOT NULL AND o.prazo_coleta != '')
                AND NOT EXISTS (
                    SELECT 1 FROM coletas c
                    WHERE c.nota_fiscal = o.nota_fiscal AND c.tipo_registro = 'fob'
                )
            """)
        except sqlite3.OperationalError as e:
            print(f"⚠️ [MIGRAÇÃO FOB] {e}")

    # População inicial de dados padrão para transportadoras
    cursor.execute("SELECT COUNT(*) FROM transportadoras")
    if cursor.fetchone()[0] == 0:
        padroes = [('SuperTime', '', ''), ('JR.Transportes', '', ''), ('Jamef', '', ''), ('TransCarioca', '', '')]
        cursor.executemany("INSERT INTO transportadoras (name, telephone, responsavel) VALUES (?, ?, ?)", padroes)

    conn.commit()
    conn.close()

# Executa e garante a estrutura completa do banco de dados na inicialização
inicializar_banco()


def inicializar_banco_seguranca():
    """Cria tabelas de segurança e usuário admin inicial apenas na primeira execução."""
    import werkzeug.security as ws

    if database_adapter.is_sqlserver():
        print("[SEGURANCA] SQL Server ativo: usuarios migrados/gerenciados no banco SistemaLogistico.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_sistema (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            nivel_hierarquico TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs_auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT NOT NULL,
            usuario TEXT NOT NULL,
            nivel TEXT NOT NULL,
            acao TEXT NOT NULL,
            detalhes TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes_painel (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    cursor.execute(
        "INSERT OR IGNORE INTO configuracoes_painel (chave, valor) VALUES ('missao', ?)",
        ('Nossa missão é movimentar o progresso com precisão logística e excelência operacional.',)
    )

    cursor.execute("SELECT COUNT(*) FROM usuarios_sistema")
    if cursor.fetchone()[0] == 0:
        senha_inicial = os.environ.get('ADMIN_SENHA_INICIAL') or os.urandom(6).hex()
        senha_cripto = ws.generate_password_hash(senha_inicial)
        cursor.execute(
            "INSERT INTO usuarios_sistema (nome, login, senha_hash, nivel_hierarquico) VALUES (?, ?, ?, ?)",
            ("Administrador", "admin", senha_cripto, "ADMIN"),
        )
        print(f"✔️ [SEGURANÇA] Usuário admin inicial criado. Senha inicial: {senha_inicial}")

    conn.commit()
    conn.close()


inicializar_banco_seguranca()


def registrar_log_operacional(acao, detalhes=""):
    """Grava na tabela de auditoria quem realizou a ação no pátio ou faturamento."""
    try:
        user = session.get('usuario_nome', 'Sistema/Desconhecido')
        nivel = session.get('usuario_nivel', 'N/A')
        agora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO logs_auditoria (data_hora, usuario, nivel, acao, detalhes) VALUES (?, ?, ?, ?, ?)",
            (agora, user, nivel, acao, detalhes),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao registrar log de auditoria: {e}")


def upsert_entrega_efetuada(cursor, nota_fiscal, data_entrega=None, recebedor=None, assinatura=None):
    """Insere ou atualiza uma entrega usando sintaxe compativel com o backend ativo."""
    if database_adapter.is_sqlserver():
        cursor.execute("SELECT id FROM entregas_efetuadas WHERE nota_fiscal = ?", (nota_fiscal,))
        existente = cursor.fetchone()
        if existente:
            sets = []
            params = []
            if data_entrega is not None:
                sets.append("data_entrega = ?")
                params.append(data_entrega)
            if recebedor is not None:
                sets.append("recebedor = ?")
                params.append(recebedor)
            if assinatura is not None:
                sets.append("assinatura = ?")
                params.append(assinatura)
            if sets:
                params.append(nota_fiscal)
                cursor.execute(
                    f"UPDATE entregas_efetuadas SET {', '.join(sets)} WHERE nota_fiscal = ?",
                    tuple(params),
                )
        else:
            cursor.execute(
                """
                INSERT INTO entregas_efetuadas (nota_fiscal, data_entrega, recebedor, assinatura)
                VALUES (?, ?, ?, ?)
                """,
                (nota_fiscal, data_entrega, recebedor, assinatura),
            )
        return

    cursor.execute(
        """
        INSERT INTO entregas_efetuadas (nota_fiscal, data_entrega, recebedor, assinatura)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(nota_fiscal) DO UPDATE SET
            data_entrega = COALESCE(excluded.data_entrega, entregas_efetuadas.data_entrega),
            recebedor = COALESCE(excluded.recebedor, entregas_efetuadas.recebedor),
            assinatura = COALESCE(excluded.assinatura, entregas_efetuadas.assinatura)
        """,
        (nota_fiscal, data_entrega, recebedor, assinatura),
    )


def login_requerido(niveis_permitidos=None):
    """Bloqueia rotas sem sessão válida. APIs retornam JSON 401."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'usuario_id' not in session:
                if request.path.startswith('/api/') or request.is_json:
                    return jsonify({"status": "erro", "mensagem": "Não autenticado"}), 401
                return redirect('/login')
            if niveis_permitidos and session.get('usuario_nivel') not in niveis_permitidos and session.get('usuario_nivel') != 'ADMIN':
                if request.path.startswith('/api/') or request.is_json:
                    return jsonify({"status": "erro", "mensagem": "Acesso negado"}), 403
                return (
                    "<body style='background:#0f172a;color:#ef4444;font-family:monospace;padding:50px;text-align:center;'>"
                    f"<h2>ACESSO NEGADO</h2><p>Perfil {session.get('usuario_nivel')} sem permissão.</p>"
                    "<a href='javascript:history.back()' style='color:#38bdf8;'>Voltar</a></body>",
                    403,
                )
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def _garantir_colunas_coletas_fob(cursor):
    """Garante colunas FOB na tabela coletas."""
    colunas = [
        ("tratativa", "TEXT"), ("motivo", "TEXT"), ("prazo_coleta", "TEXT"),
        ("transp_coleta", "TEXT"), ("contato_celular", "TEXT"), ("contato_email", "TEXT"),
        ("tipo_registro", "TEXT"),
    ]
    cursor.execute("PRAGMA table_info(coletas)")
    existentes = {c[1] for c in cursor.fetchall()}
    for col, tipo in colunas:
        if col not in existentes:
            try:
                cursor.execute(f"ALTER TABLE coletas ADD COLUMN {col} {tipo}")
            except sqlite3.OperationalError:
                pass

# ============================================================
# 🔥 COLA O CÓDIGO DA MIGRAÇÃO EXATAMENTE AQUI (PONTO 1)
# ============================================================
def migrar_excel_motivos_para_sqlite():
    if database_adapter.is_sqlserver():
        return

    caminho_excel_motivos = os.path.join(BASE_DIR, 'templates', 'LISTA_MOTIVOS.xlsx')
    if not os.path.exists(caminho_excel_motivos):
        caminho_excel_motivos = EXCEL_LISTA_MOTIVOS
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS motivos_ocorrencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            motivo TEXT NOT NULL UNIQUE
        )
    """)
    if os.path.exists(caminho_excel_motivos):
        try:
            df = pd.read_excel(caminho_excel_motivos)
            if not df.empty:
                df = df.fillna("")
                dados_para_inserir = []
                for cod, mot in zip(df.iloc[:, 0], df.iloc[:, 1]):
                    cod = str(cod).strip().replace('.0', '')
                    mot = str(mot).strip()
                    texto_motivo = f"{cod} - {mot}" if cod and mot else mot
                    if texto_motivo:
                        dados_para_inserir.append((texto_motivo,))
                cursor.executemany("INSERT OR IGNORE INTO motivos_ocorrencias (motivo) VALUES (?)", dados_para_inserir)
                conn.commit()
                print(f"✔️ [BANCO DE DADOS] Planilha LISTA_MOTIVOS consolidada no SQLite.")
        except Exception as e:
            print(f"❌ Erro ao processar planilha de motivos: {e}")
    conn.close()

migrar_excel_motivos_para_sqlite()

def ler_motivos_ocorrencias_db():
    try:
        conn = get_db_connection() # Conexão unificada
        cursor = conn.cursor()
        cursor.execute("SELECT motivo FROM motivos_ocorrencias ORDER BY id ASC")
        motivos = [row['motivo'] for row in cursor.fetchall()] # Lendo diretamente via Row
        conn.close()
        return motivos
    except Exception as e:
        print(f"Erro ao ler motivos do SQLite: {e}")
        return []
# ============================================================

# ============================================================
# ⚙️ MÓDULO CRUD: GERENCIADOR COMPLETO DE MOTIVOS DE OCORRÊNCIAS
# ============================================================
@app.route('/gerenciar_motivos', methods=['GET'])
def tela_gerenciar_motivos():
    """Renderiza a nova interface mestre de manutenção de motivos de ocorrências."""
    if 'usuario_id' not in session:
        return redirect('/login')
    return render_template('gerenciar_motivos.html')

@app.route('/api/obter_motivos_gerenciador', methods=['GET'])
@login_requerido()
def api_obter_motivos_gerenciador():
    """Busca a lista de motivos estruturada com ID para alimentar o Grid do painel."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, motivo FROM motivos_ocorrencias ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()
        
        resultado = [{"id": r["id"], "motivo": r["motivo"]} for r in rows]
        return jsonify(resultado)
    except Exception as e:
        return jsonify([])

@app.route('/api/salvar_motivo_gerenciador', methods=['POST'])
@login_requerido()
def api_salvar_motivo_gerenciador():
    """Realiza a inclusão de um novo motivo ou atualiza uma descrição existente via ID."""
    try:
        dados = request.get_json() or {}
        id_reg = _id_str(dados.get('id'))
        motivo_texto = dados.get('motivo', '').strip()

        if not motivo_texto:
            return jsonify({"status": "erro", "mensagem": "A descrição do motivo é obrigatória!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        if id_reg:
            # MODO ALTERAÇÃO
            cursor.execute("UPDATE motivos_ocorrencias SET motivo = ? WHERE id = ?", (motivo_texto, id_reg))
            msg = "Motivo operacional atualizado com sucesso!"
        else:
            # MODO INCLUSÃO (Garante a restrição UNIQUE para não duplicar registros idênticos)
            cursor.execute("SELECT id FROM motivos_ocorrencias WHERE motivo = ?", (motivo_texto,))
            if cursor.fetchone():
                conn.close()
                return jsonify({"status": "erro", "mensagem": "Este motivo já está cadastrado no sistema!"}), 400
                
            cursor.execute("INSERT INTO motivos_ocorrencias (motivo) VALUES (?)", (motivo_texto,))
            msg = "Novo motivo de ocorrência incluído com sucesso na base!"

        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": msg})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/excluir_motivo_gerenciador', methods=['POST'])
@login_requerido()
def api_excluir_motivo_gerenciador():
    """Remove definitivamente a diretriz de motivo selecionada direto da tabela do SQLite."""
    try:
        dados = request.get_json() or {}
        id_reg = dados.get('id')

        if not id_reg:
            return jsonify({"status": "erro", "mensagem": "ID do registro inválido!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM motivos_ocorrencias WHERE id = ?", (id_reg,))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "sucesso", "mensagem": "Motivo removido com sucesso da base de dados!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
@app.route('/validar_canhoto')
@login_requerido()
def tela_validar_canhoto():
    """Chama o painel duplo de validação assistida de canhotos com suporte a zoom"""
    return render_template('validar_canhoto.html')    

# ============================================================
# 🔥 MOTOR DE CONCILIAÇÃO LOGÍSTICA BLINDADO CONTRA ERROS DE DIGITAÇÃO
# ============================================================
def conciliar_faturamento_automatico(nota_fiscal_str, motorista, assinatura_dados, usuario_baixa="PORTARIA", data_entrega=None):
    """
    Registra baixa em entregas_efetuadas para cada NF do lote.
    Não altera transportadora no faturamento (campo corporativo).
    """
    try:
        if not nota_fiscal_str:
            return

        notas_individuais = [n.strip() for n in str(nota_fiscal_str).split(',') if n.strip()]
        if not notas_individuais:
            return

        data_entrega_atual = data_entrega or datetime.now().strftime('%d/%m/%Y')
        recebedor_formatado = f"MOT: {str(motorista).upper().strip()}"
        texto_auditoria = f"{assinatura_dados} | BAIXA POR: {str(usuario_baixa).upper().strip()}"

        conn = get_db_connection()
        cursor = conn.cursor()

        for nf in notas_individuais:
            nf_limpa = nf.lstrip('0').strip()
            if not nf_limpa:
                continue
            upsert_entrega_efetuada(
                cursor,
                nf_limpa,
                data_entrega_atual,
                recebedor_formatado,
                texto_auditoria,
            )

        conn.commit()
        conn.close()
        print(f"✔️ [CONCILIAÇÃO] Baixa gravada para NFs: {notas_individuais} | Data: {data_entrega_atual}")
    except Exception as e:
        print(f"❌ [ERRO CONCILIAÇÃO] Falha ao amarrar faturamento: {str(e)}")


# ============================================================
# FUNÇÕES AUXILIARES DE SISTEMA E EXCEL
# ============================================================

import os

def buscar_ultimo_faturamento():
    """
    Busca automaticamente o Excel de faturamento mais recente 
    diretamente na mesma pasta onde o aplicativo está rodando.
    """
    # 👑 O SEGREDO DA REDE: Descobre dinamicamente a pasta onde o app está sendo executado
    import sys
    if getattr(sys, 'frozen', False):
        # Se estiver rodando como um executável (.exe) compactado pelo PyInstaller
        pasta = os.path.dirname(sys.executable)
    else:
        # Se estiver rodando direto pelo script Python (app.py)
        pasta = os.path.dirname(os.path.abspath(__file__))

    if not os.path.exists(pasta):
        print(f"⚠️ [ERRO DE PASTA] Diretório não encontrado: {pasta}")
        return None

    # Varre a pasta do app procurando pelo padrão do arquivo
    arquivos = [
        os.path.join(pasta, f)
        for f in os.listdir(pasta)
        if f.lower().startswith("nf-e_emitidas_endereços") 
        and f.lower().endswith(".xlsx") 
        and not f.startswith("~$")  # Filtra arquivos temporários ocultos do Excel
    ]
    
    if not arquivos:
        print(f"⚠️ [AVISO] Nenhum arquivo 'NF-e_emitidas_endereços' encontrado em: {pasta}")
        return None
        
    # Ordena os arquivos deixando o modificado mais recentemente na posição [0]
    arquivos.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    print(f"✔️ [ARQUIVO DETECTADO] Lendo o faturamento: {os.path.basename(arquivos[0])}")
    return arquivos[0]


def buscar_ultima_expedicao():
    pasta = PASTA_DOWNLOADS
    if not os.path.exists(pasta):
        return None
    arquivos = [
        f for f in glob.glob(os.path.join(pasta, "Notas_Expedidas_-_Relatório*.xlsx"))
        if not os.path.basename(f).startswith("~$")
    ]
    return max(arquivos, key=os.path.getmtime) if arquivos else None


def garantir_pasta_uploads_manual():
    os.makedirs(PASTA_UPLOADS_MANUAL, exist_ok=True)


def obter_planilha_expedicao_conciliacao():
    """Prioriza planilha enviada manualmente pelo navegador do cliente; senão, busca no servidor."""
    if os.path.exists(ARQUIVO_EXPEDICAO_MANUAL):
        return ARQUIVO_EXPEDICAO_MANUAL
    return buscar_ultima_expedicao()


def buscar_ultimo_wms_apontamento():
    """Localiza o template wms_apontamento mais recente no servidor ou na pasta do app."""
    padroes = []
    for pasta in (PASTA_DOWNLOADS, BASE_DIR):
        if pasta and os.path.exists(pasta):
            padroes.extend([
                os.path.join(pasta, "wms_apontamento*.xls*"),
                os.path.join(pasta, "wms apontamento*.xls*"),
                os.path.join(pasta, "*wms*apont*.xls*"),
                os.path.join(pasta, "*apontamento*wms*.xls*"),
            ])
    arquivos = []
    for padrao in padroes:
        arquivos.extend([
            f for f in glob.glob(padrao)
            if not os.path.basename(f).startswith("~$")
        ])
    return max(set(arquivos), key=os.path.getmtime) if arquivos else None


def obter_planilha_wms_conciliacao():
    """Prioriza WMS enviado manualmente; senao busca template wms_apontamento no servidor."""
    if os.path.exists(ARQUIVO_WMS_MANUAL):
        return ARQUIVO_WMS_MANUAL
    return buscar_ultimo_wms_apontamento()


def info_ultima_atualizacao_manual():
    """Metadados das importações manuais para exibir no painel."""
    info = {'faturamento': None, 'expedicao': None, 'wms': None}
    for chave, caminho in (
        ('faturamento', ARQUIVO_FATURAMENTO_MANUAL),
        ('expedicao', ARQUIVO_EXPEDICAO_MANUAL),
        ('wms', ARQUIVO_WMS_MANUAL),
    ):
        if os.path.exists(caminho):
            ts = datetime.fromtimestamp(os.path.getmtime(caminho))
            info[chave] = {
                'arquivo': os.path.basename(caminho),
                'data_hora': ts.strftime('%d/%m/%Y %H:%M'),
            }
    return info


_cache_importacoes = {
    'faturamento': None,
    'expedicao_dict': None,
    'expedicao_df': None,
    'wms_dict': None,
}


def invalidar_cache_faturamento():
    _cache_importacoes['faturamento'] = None


def invalidar_cache_expedicao():
    _cache_importacoes['expedicao_dict'] = None
    _cache_importacoes['expedicao_df'] = None


def invalidar_cache_wms():
    _cache_importacoes['wms_dict'] = None


def obter_planilha_faturamento_conciliacao():
    """Prioriza planilha enviada manualmente; senão, busca na pasta do app."""
    if os.path.exists(ARQUIVO_FATURAMENTO_MANUAL):
        return ARQUIVO_FATURAMENTO_MANUAL
    return buscar_ultimo_faturamento()


def importar_faturamento_se_necessario(caminho_excel):
    """Importa faturamento só quando o arquivo mudou (evita lentidão a cada refresh)."""
    if not caminho_excel or not os.path.exists(caminho_excel):
        return
    chave = (caminho_excel, os.path.getmtime(caminho_excel))
    if _cache_importacoes['faturamento'] == chave:
        return
    importar_faturamento_para_sqlite(caminho_excel)
    _cache_importacoes['faturamento'] = chave


def _validar_extensao_planilha(nome_arquivo):
    return nome_arquivo and nome_arquivo.lower().endswith(('.xlsx', '.xls'))


def _limpar_numero_nf(valor):
    """Remove sufixo .0 do Excel e padroniza NF para exibição e conciliação."""
    if valor is None:
        return ''
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass
    s = str(valor).strip()
    if s.lower() in ('nan', 'none', '-', 'nat', ''):
        return ''
    return re.sub(r'\.0$', '', s)


def _resolver_colunas_expedicao(df_exp):
    """Identifica colunas NF e data com fallbacks seguros."""
    cols = list(df_exp.columns)
    if not cols:
        raise ValueError('A planilha não possui colunas reconhecíveis.')
    col_nf = next((c for c in cols if 'nota' in str(c).lower()), None)
    col_data = next((c for c in cols if 'emiss' in str(c).lower() or 'data' in str(c).lower()), None)
    if col_nf is None:
        col_nf = cols[min(7, len(cols) - 1)]
    if col_data is None:
        col_data = cols[min(1, len(cols) - 1)]
    return col_nf, col_data


def _ffill_colunas_dataframe(df, colunas=None):
    """Propaga valores de células mescladas/vazias (formato Nomus/Excel)."""
    cols = colunas if colunas is not None else list(df.columns)
    for col in cols:
        if col not in df.columns:
            continue
        df[col] = df[col].replace(r'^\s*$', pd.NA, regex=True)
        if df[col].dtype == object:
            df[col] = df[col].replace(['nan', 'None', '-', 'NaT'], pd.NA)
        df[col] = df[col].ffill()
    return df


def normalizar_dataframe_expedicao(df):
    """
    Tratativa Nomus: propaga dados das linhas de cima (ffill), separa NFs múltiplas
    em linhas individuais (explode) e replica demais colunas em cada linha criada.
    Retorna (df_normalizado, col_nf, col_data).
    """
    if df is None or df.empty:
        raise ValueError('A planilha de expedição está vazia.')

    df = df.copy()
    col_nf, col_data = _resolver_colunas_expedicao(df)

    df = _ffill_colunas_dataframe(df)

    df[col_nf] = (
        df[col_nf].astype(str)
        .str.replace(r'\.0$', '', regex=True)
        .str.replace(';', ',')
        .str.replace('\r\n', ',')
        .str.replace('\n', ',')
        .str.replace('\r', ',')
    )
    df[col_nf] = df[col_nf].str.split(',')
    df = df.explode(col_nf, ignore_index=True)
    df[col_nf] = df[col_nf].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

    invalid_nf = {'', 'nan', 'none', '-', 'nat'}
    df = df[~df[col_nf].str.lower().isin(invalid_nf)].copy()

    df = _ffill_colunas_dataframe(df, [c for c in df.columns if c != col_nf])

    return df, col_nf, col_data


def carregar_dataframe_expedicao(caminho_excel):
    """Carrega expedição com cache por arquivo; manual já vem normalizado no upload."""
    if not caminho_excel or not os.path.exists(caminho_excel):
        raise ValueError('Arquivo de expedição não encontrado.')
    chave = (caminho_excel, os.path.getmtime(caminho_excel))
    cached = _cache_importacoes.get('expedicao_df')
    if cached and cached[0] == chave:
        return cached[1]

    df = pd.read_excel(caminho_excel)
    cols = list(df.columns)
    if caminho_excel == ARQUIVO_EXPEDICAO_MANUAL:
        col_nf, col_data = _resolver_colunas_expedicao(df)
    else:
        df, col_nf, col_data = normalizar_dataframe_expedicao(df)

    df[col_nf] = df[col_nf].apply(_limpar_numero_nf)

    resultado = (df, col_nf, col_data, cols)
    _cache_importacoes['expedicao_df'] = (chave, resultado)
    return resultado


def mapear_dict_expedicao_de_excel(caminho_excel):
    """Lê planilha de expedição e retorna dicionário NF -> data expedição."""
    dict_expedidas = {}
    if not caminho_excel or not os.path.exists(caminho_excel):
        return dict_expedidas

    chave = (caminho_excel, os.path.getmtime(caminho_excel))
    cached = _cache_importacoes.get('expedicao_dict')
    if cached and cached[0] == chave:
        return cached[1]

    df_exp, col_nf_v, col_data_v, _ = carregar_dataframe_expedicao(caminho_excel)
    for nf_raw, dt_raw in zip(df_exp[col_nf_v], df_exp[col_data_v]):
        nf_str_exp = _limpar_numero_nf(nf_raw)
        if nf_str_exp:
            dict_expedidas[nf_str_exp] = {
                "data_expedicao": str(dt_raw).split()[0] if pd.notna(dt_raw) else "-"
            }

    if not dict_expedidas:
        raise ValueError('Nenhuma nota fiscal válida encontrada na planilha. Verifique o arquivo «Notas_Expedidas».')

    _cache_importacoes['expedicao_dict'] = (chave, dict_expedidas)
    return dict_expedidas

def _normalizar_nome_coluna(valor):
    import unicodedata
    texto = unicodedata.normalize('NFKD', str(valor or '').lower())
    texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', ' ', texto).strip()


def _resolver_colunas_wms(df_wms):
    cols = list(df_wms.columns)
    normalizadas = {c: _normalizar_nome_coluna(c) for c in cols}

    def escolher(grupos):
        for c, nome in normalizadas.items():
            if all(any(token in nome for token in grupo) for grupo in grupos):
                return c
        return None

    col_nf = escolher([('nf', 'nota', 'fiscal', 'documento')])
    col_codigo = escolher([('codigo', 'cod', 'item', 'produto', 'material', 'sku', 'referencia')])
    col_posicao = escolher([('posicao', 'enderec', 'local', 'rua', 'box', 'wms', 'localizacao', 'deposito', 'armazem', 'estoque')])
    return col_nf, col_codigo, col_posicao


def _limpar_codigo_material(valor):
    if valor is None:
        return ''
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip().upper()
    texto = re.sub(r'\.0$', '', texto)
    return re.sub(r'[^A-Z0-9]', '', texto)


def _valor_texto_planilha(valor):
    if valor is None:
        return ''
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    if texto.lower() in ('nan', 'none', '-', 'nat'):
        return ''
    return re.sub(r'\.0$', '', texto)


def mapear_posicoes_wms_de_excel(caminho_excel):
    """Retorna mapas NF -> posicoes e codigo de material -> posicoes a partir do wms_apontamento."""
    vazio = {'por_nf': {}, 'por_codigo': {}, 'arquivo': None}
    if not caminho_excel or not os.path.exists(caminho_excel):
        return vazio

    chave = (caminho_excel, os.path.getmtime(caminho_excel))
    cached = _cache_importacoes.get('wms_dict')
    if cached and cached[0] == chave:
        return cached[1]

    por_nf = {}
    por_codigo = {}
    try:
        abas = pd.read_excel(caminho_excel, sheet_name=None)
    except Exception as e:
        print(f"⚠️ [WMS] Falha ao ler template wms_apontamento: {e}")
        return vazio

    for _, df_raw in abas.items():
        if df_raw is None or df_raw.empty:
            continue
        df = df_raw.copy().dropna(how='all')
        if df.empty:
            continue
        col_nf, col_codigo, col_posicao = _resolver_colunas_wms(df)
        if col_posicao is None:
            continue
        if col_nf:
            df = _ffill_colunas_dataframe(df, [col_nf])
        if col_codigo:
            df = _ffill_colunas_dataframe(df, [col_codigo])
        for _, row in df.iterrows():
            posicao = _valor_texto_planilha(row.get(col_posicao))
            if not posicao:
                continue
            if col_nf:
                nf = _limpar_numero_nf(row.get(col_nf))
                if nf:
                    por_nf.setdefault(nf, set()).add(posicao)
            if col_codigo:
                codigo = _limpar_codigo_material(row.get(col_codigo))
                if codigo:
                    por_codigo.setdefault(codigo, set()).add(posicao)

    resultado = {
        'por_nf': {k: sorted(v) for k, v in por_nf.items()},
        'por_codigo': {k: sorted(v) for k, v in por_codigo.items()},
        'arquivo': os.path.basename(caminho_excel),
    }
    _cache_importacoes['wms_dict'] = (chave, resultado)
    return resultado


def _posicao_wms_para_nf(nf, mapa_wms, itens_por_nf):
    nf_limpa = _limpar_numero_nf(nf)
    posicoes = []
    if nf_limpa in mapa_wms.get('por_nf', {}):
        posicoes.extend(mapa_wms['por_nf'][nf_limpa])
    for codigo in itens_por_nf.get(nf_limpa, []):
        posicoes.extend(mapa_wms.get('por_codigo', {}).get(codigo, []))
    unicas = []
    vistos = set()
    for pos in posicoes:
        chave = str(pos).strip().upper()
        if chave and chave not in vistos:
            vistos.add(chave)
            unicas.append(str(pos).strip())
    return " | ".join(unicas) if unicas else "-"


def ler_canhotos_whatsapp_vivos():
    """
    MÓDULO WHATSAPP: Varre o arquivo _chat.txt da pasta do projeto,
    vincula o texto mestre de cada linha com a sua respectiva imagem
    e gera a lista estruturada para o banco/tela da TV.
    """
    pasta_projeto = os.path.dirname(os.path.abspath(__file__))
    caminho_chat = os.path.join(pasta_projeto, "_chat.txt")
    
    if not os.path.exists(caminho_chat):
        print(f"⚠️ [WHATSAPP] Arquivo de conversas não localizado em: {caminho_chat}")
        return []

    # Regex ajustada milimetricamente para o padrão do teu _chat.txt
    padrao_linha = re.compile(r'\[(\d{2}/\d{2}/\d{4}),\s(\d{2}:\d{2}:\d{2})\]\s([^:]+):\s(.*)')
    padrao_logistico = re.compile(r'(\d{5})\s+([A-Za-z0-9\s!\.\-\/]+?)\s+(\d+)\s*[vV]')
    
    historico_mensagens = []
    lista_canhotos_finais = []

    try:
        with open(caminho_chat, 'r', encoding='utf-8') as f:
            for linha in f:
                linha_limpa = linha.replace('\u200e', '').replace('\u200f', '').strip()
                match = padrao_linha.search(linha_limpa)
                
                if match:
                    data, hora, usuario, conteudo = match.groups()
                    has_image = "<anexado:" in conteudo or "arquivo anexado" in conteudo.lower()
                    nome_arquivo = ""
                    
                    if has_image:
                        extracao_foto = re.search(r'<(anexado|arquivo anexado):\s*([^>]+)>', conteudo, re.IGNORECASE)
                        if extracao_foto:
                            nome_arquivo = extracao_foto.group(2).strip()
                        texto_puro = re.sub(r'<(anexado|arquivo anexado):\s*[^>]+>', '', conteudo, flags=re.IGNORECASE).strip()
                    else:
                        texto_puro = conteudo.strip()

                    historico_mensagens.append({
                        "data_hora": f"{data} {hora}",
                        "usuario": usuario.strip(),
                        "texto_puro": texto_puro,
                        "has_image": has_image,
                        "nome_arquivo": nome_arquivo
                    })
                else:
                    if historico_mensagens:
                        historico_mensagens[-1]["texto_puro"] += " " + linha_limpa

        # Cria o vínculo retroativo
        for i, msg in enumerate(historico_mensagens):
            if msg["has_image"]:
                texto_legenda = msg["texto_puro"]
                
                if not texto_legenda and i > 0:
                    msg_anterior = historico_mensagens[i - 1]
                    if not msg_anterior["has_image"] and msg_anterior["usuario"] == msg["usuario"]:
                        texto_legenda = msg_anterior["texto_puro"]

                nf_detectada = "-"
                cliente_detectado = "NÃO IDENTIFICADO"
                volumes_detectados = "1"
                
                match_log = padrao_logistico.search(texto_legenda)
                if match_log:
                    nf_detectada, cliente_detectado, volumes_detectados = match_log.groups()
                else:
                    busca_nf = re.search(r'\b(\d{5})\b', texto_legenda)
                    if busca_nf:
                        nf_detectada = busca_nf.group(1)

                lista_canhotos_finais.append({
                    "data_hora": msg["data_hora"],
                    "operador": msg["usuario"],
                    "arquivo_foto": msg["nome_arquivo"],
                    "texto_original": texto_legenda if texto_legenda else "[Apenas imagem]",
                    "nf": nf_detectada,
                    "cliente": cliente_detectado.strip().upper(),
                    "volumes": volumes_detectados
                })
                
        # Retorna a lista invertida para mostrar as mídias mais recentes do pátio no topo da TV
        return lista_canhotos_finais[::-1]

    except Exception as e:
        print(f"❌ Erro ao processar o log do WhatsApp: {str(e)}")
        return []


def importar_faturamento_para_sqlite(caminho_excel):
    df = pd.read_excel(caminho_excel)
    if df.empty:
        print("⚠️ [FATURAMENTO] Planilha vazia — importação cancelada para preservar o banco.")
        return

    colunas_para_replicar = [
        'Emissão da NF-e', 'Cliente', 'Endereço', 'Município', 'UF', 'CEP', 
        'Transportadora', 'Modalidade', 'Volumes', 'Especie', 'Peso bruto NF', 
        'Pedido', 'Valor total da NF-e'
    ]
    for col in colunas_para_replicar:
        if col in df.columns:
            df[col] = df[col].ffill()

    df = df.fillna("")

    if 'Número da NF-e' in df.columns:
        df['Número da NF-e'] = (
            df['Número da NF-e']
            .astype(str)
            .str.replace(r'\.0$', '', regex=True)
            .str.strip()
        )

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM faturamento")
        cur.execute("DELETE FROM faturamento_itens")

        faturamentos_salvos = set()
        dados_faturamento = []
        dados_itens = []

        for _, row in df.iterrows():
            nf = row["Número da NF-e"]
            if not nf:
                continue

            if nf not in faturamentos_salvos:
                dados_faturamento.append((
                    nf, str(row["Emissão da NF-e"]), row["Cliente"], row["Endereço"],
                    row["Município"], row["UF"], row["CEP"], row["Transportadora"],
                    row["Modalidade"], str(row["Volumes"]), row["Especie"],
                    str(row["Peso bruto NF"]), str(row["Pedido"]), str(row["Valor total da NF-e"])
                ))
                faturamentos_salvos.add(nf)

            dados_itens.append((
                nf,
                str(row.get("Código item", "")).strip(),
                str(row.get("Descrição do item", "")).strip(),
                str(row.get("Qtde", "")).strip(),
                str(row.get("U.M.", "")).strip(),
                str(row.get("Peso unitário do item", "")).strip(),
                str(row.get("Peso total do item", "")).strip()
            ))

        if dados_faturamento:
            cur.executemany("""
                INSERT INTO faturamento (
                    nf, emissao, cliente, endereco, municipio, uf, cep,
                    transportadora, modalidade, volumes, especie, peso_bruto_nf, pedido, valor_total_nf
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, dados_faturamento)

        if dados_itens:
            cur.executemany("""
                INSERT INTO faturamento_itens (
                    nf, codigo_item, descricao_item, qtde, um, peso_unitario, peso_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, dados_itens)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ler_lista_do_excel():
    itens = []
    if not os.path.exists(EXCEL_LISTA_MOTIVOS):
        return itens
    try:
        df = pd.read_excel(EXCEL_LISTA_MOTIVOS)
        if df.shape[0] >= 1:
            df = df.fillna("")
            for cod, mot in zip(df.iloc[:, 0], df.iloc[:, 1]):
                cod = str(cod).strip()
                mot = str(mot).strip()
                if cod and mot:
                    itens.append(f"{cod} - {mot}")
                elif mot:
                    itens.append(mot)
    except Exception as e:
        print(f"ERRO ao ler a lista de motivos do Excel: {e}")
    return itens


def ler_transportadoras_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM transportadoras ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ============================================================
# ROTAS DE RENDERIZAÇÃO DAS TELAS E INICIALIZAÇÃO
# ============================================================

# ============================================================
# ROTAS DE RENDERIZAÇÃO DAS TELAS E INICIALIZAÇÃO
# ============================================================

@app.route('/tv_pracas')
def tv_pracas():
    return render_template('pracas_atendimento.html')

def obter_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.10.193" # IP padrão de garantia


def obter_porta_atual():
    try:
        if request.host and ':' in request.host:
            return int(request.host.rsplit(':', 1)[1])
    except Exception:
        pass
    return int(os.environ.get('PORTA_SERVIDOR', 5000))


def listar_ips_rede_local():
    """Coleta localhost + todos os IPv4 ativos da máquina (ipconfig + rota padrão)."""
    ips = {'127.0.0.1'}
    try:
        proc = subprocess.run(
            ['ipconfig'],
            capture_output=True,
            text=True,
            errors='ignore',
            timeout=8,
            shell=True,
        )
        for match in re.finditer(r'IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)', proc.stdout or ''):
            ip = match.group(1).strip()
            if not ip.startswith('169.254.'):
                ips.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        ips.add(obter_ip_local())
    return sorted(ips, key=lambda x: (0 if x == '127.0.0.1' else 1, x))


def montar_dados_catalogo_portal(porta=None):
    porta = porta or 5000
    enderecos = []
    for ip in listar_ips_rede_local():
        rotulo = 'Localhost (esta máquina)' if ip == '127.0.0.1' else f'Rede LAN — {ip}'
        base = f'http://{ip}:{porta}'
        enderecos.append({
            'ip': ip,
            'rotulo': rotulo,
            'base_url': base,
            'portal_url': f'{base}/portal_operacional',
            'login_url': f'{base}/login',
        })

    links_rede = []
    for grupo in MODULOS_CATALOGO:
        for item in grupo['itens']:
            for end in enderecos:
                links_rede.append({
                    'grupo': grupo['titulo'],
                    'grupo_id': grupo['id'],
                    'titulo': item['titulo'],
                    'url_path': item['url'],
                    'ip': end['ip'],
                    'ip_rotulo': end['rotulo'],
                    'link_completo': end['base_url'] + item['url'],
                    'nova_aba': item.get('nova_aba', False),
                    'admin_only': item.get('admin_only', False),
                })

    return {
        'catalogo': MODULOS_CATALOGO,
        'enderecos': enderecos,
        'porta': porta,
        'links_rede': links_rede,
        'ip_principal': obter_ip_local(),
    }


# Rota raiz unificada — ver portal_ignicao_login mais abaixo
# ============================================================
# 🟢 ROTAS DE RENDERIZAÇÃO ADAPTADAS PARA O FORMATO SUSPENSO (PONTO 2)
# ============================================================
# ============================================================
# 🚛 MÓDULO CORE: CENTRAL DE SOLICITAÇÃO DE COLETAS FOB (INDEX)
# ============================================================
@app.route('/formulario', methods=['GET'])
def index_coletas_fob():
    """Renderiza a nova Central de Solicitação de Coletas FOB com grid e farol temporal."""
    if 'usuario_id' not in session:
        return redirect('/login')
    return render_template('index.html')


@app.route('/api/listar_coletas_fob_grid', methods=['GET'])
@login_requerido()
def api_listar_coletas_fob_grid():
    """Busca o histórico de solicitações de coletas FOB diretamente do SQLite."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _garantir_colunas_coletas_fob(cursor)

        cursor.execute("""
            SELECT id, cliente, nota_fiscal, data_solicitacao, tratativa, motivo,
                   prazo_coleta, transp_coleta, contato_celular, contato_email
            FROM coletas
            WHERE tipo_registro = 'fob' OR status = 'FOB'
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        resultado = [{
            "id": r[0],
            "cliente": r[1] or "",
            "nota_fiscal": r[2] or "",
            "data": r[3] or "",
            "tratativa": r[4] or "",
            "motivo": r[5] or "",
            "prazo_coleta": r[6] or "",
            "transp_coleta": r[7] or "",
            "contato_celular": r[8] or "",
            "contato_email": r[9] or "",
        } for r in rows]
        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Erro ao listar coletas FOB: {e}")
        return jsonify([])


@app.route('/api/salvar_coleta_fob_grid', methods=['POST'])
@login_requerido()
def api_salvar_coleta_fob_grid():
    """Insere ou atualiza os dados da solicitação de coleta FOB no banco."""
    try:
        dados = request.get_json() or {}
        id_reg = _id_str(dados.get('id'))
        cliente = dados.get('cliente', '').strip()
        nf = dados.get('nota_fiscal', '').strip()
        data_solicitacao = dados.get('data', '').strip()
        tratativa = dados.get('tratativa', '').strip()
        motivo = dados.get('motivo', '').strip()
        prazo_coleta = dados.get('prazo_coleta', '').strip()
        transp_coleta = dados.get('transp_coleta', '').strip()
        contato_celular = dados.get('contato_celular', '').strip()
        contato_email = dados.get('contato_email', '').strip()

        if not cliente or not nf or not transp_coleta:
            return jsonify({"status": "erro", "mensagem": "Cliente, NF e Transportadora Coletora são obrigatórios!"}), 400

        if "-" in data_solicitacao:
            try:
                data_solicitacao = datetime.strptime(data_solicitacao, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                pass
        if "-" in prazo_coleta:
            try:
                prazo_coleta = datetime.strptime(prazo_coleta, '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                pass

        conn = get_db_connection()
        cursor = conn.cursor()
        _garantir_colunas_coletas_fob(cursor)

        if id_reg:
            cursor.execute("""
                UPDATE coletas SET
                    cliente = ?, nota_fiscal = ?, data_solicitacao = ?, tratativa = ?, motivo = ?,
                    prazo_coleta = ?, transp_coleta = ?, contato_celular = ?, contato_email = ?,
                    transportadora = ?, status = 'FOB', tipo_registro = 'fob'
                WHERE id = ?
            """, (cliente, nf, data_solicitacao, tratativa, motivo, prazo_coleta, transp_coleta,
                  contato_celular, contato_email, transp_coleta, id_reg))
            msg = f"Solicitação de Coleta da NF {nf} atualizada com sucesso!"
        else:
            cursor.execute("""
                INSERT INTO coletas (
                    cliente, nota_fiscal, transportadora, data_solicitacao, status,
                    tratativa, motivo, prazo_coleta, transp_coleta, contato_celular, contato_email, tipo_registro
                ) VALUES (?, ?, ?, ?, 'FOB', ?, ?, ?, ?, ?, ?, 'fob')
            """, (cliente, nf, transp_coleta, data_solicitacao, tratativa, motivo, prazo_coleta,
                  transp_coleta, contato_celular, contato_email))
            msg = f"Nova solicitação de Coleta FOB para a NF {nf} registrada!"

        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": msg})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

# 🚚 ROTA EXCLUSIVA PARA A INTERFACE MOBILE OFFLINE DO MOTORISTA
@app.route('/canhoto_motorista')
def tela_canhoto_motorista():
    lista_transp = ler_transportadoras_db()
    return render_template('canhoto_motorista.html', transportadoras=lista_transp)

@app.route('/cadastro_transportadora')
def cadastro_transportadora():
    return redirect('/gerenciar_transportadoras')

@app.route('/torre_controle')
def torre_controle():
    return render_template('torre_controle.html')

@app.route('/auditoria_torre')
def auditoria_torre():
    return render_template('torre_auditora.html') 

# ============================================================
# 📡 ROTA DA TORRE: MANUAL VIVO DE INSTRUÇÃO DE IP (MODO TV)
# ============================================================
@app.route('/template_ip', methods=['GET'])
def template_ip():
    """ Renderiza na TV os links de IP dinâmicos para instrução do pátio """
    ip_atual = obter_ip_local()
    return render_template('template_ip.html', ip_servidor=ip_atual)

# ============================================================
# MÓDULO LOGÍSTICO: INTERFACE DE TORRE DE CONTROLE (API JSON)
# ============================================================

@app.route('/api/metricas_torre')
def metricas_torre():
    data_filtro = request.args.get('data', '').strip()

    if data_filtro:
        try:
            dt_base = datetime.strptime(data_filtro, '%Y-%m-%d').date()
        except Exception:
            dt_base = datetime.today().date()
    else:
        dt_base = datetime.today().date()

    primeiro_dia = dt_base.replace(day=1)
    ultimo_dia = (primeiro_dia + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    pasta_downloads = PASTA_DOWNLOADS

    # --- CROSS LOGÍSTICO ---
    padrao_expedicao = os.path.join(pasta_downloads, "Notas_Expedidas_-_Relatório*.xlsx")
    arquivos_expedicao = glob.glob(padrao_expedicao)
    dict_expedicao = {}
    
    if arquivos_expedicao:
        arquivos_expedicao.sort(key=os.path.getmtime)
        ultimo_exp = arquivos_expedicao[-1]
        try:
            df_exp = pd.read_excel(ultimo_exp)
            if not df_exp.empty:
                cols_exp = list(df_exp.columns)
                df_exp, c_nf, c_data_exp = normalizar_dataframe_expedicao(df_exp)
                c_transp = next((c for c in cols_exp if 'transp' in str(c).lower()), cols_exp[min(3, len(cols_exp) - 1)])
                c_mot = next((c for c in cols_exp if 'motor' in str(c).lower()), cols_exp[min(4, len(cols_exp) - 1)])
                c_obs = next((c for c in cols_exp if 'obs' in str(c).lower()), cols_exp[min(10, len(cols_exp) - 1)] if len(cols_exp) > 10 else None)

                for _, r in df_exp.iterrows():
                    nf_exp = _limpar_numero_nf(r[c_nf])
                    if nf_exp:
                        dict_expedicao[nf_exp] = {
                            "data_exp": str(r[c_data_exp]).split()[0] if pd.notna(r[c_data_exp]) else "Pendente",
                            "transportadora": str(r[c_transp]).strip() if pd.notna(r[c_transp]) else "-",
                            "motorista": str(r[c_mot]).strip() if pd.notna(r[c_mot]) else "-",
                            "observacoes": str(r[c_obs]).strip() if c_obs and pd.notna(r[c_obs]) else ""
                        }
            print(f"✔️ [TORRE] {len(dict_expedicao)} notas fiscalizadas com sucesso.")
        except Exception as e:
            print(f"❌ Erro ao cruzar arquivo de expedição na torre: {str(e)}")

    # 📥 GATILHO ATIVADO: Força a atualização da base SQLite via pasta Downloads local antes de processar
    excel_fat = buscar_ultimo_faturamento()
    df_excel = pd.DataFrame()

    if excel_fat:
        try:
            # Sincroniza o banco físico com o arquivo mais novo
            importar_faturamento_para_sqlite(excel_fat)
            df_excel = pd.read_excel(excel_fat)
            print(f"✔️ [MOTOR TV] Banco de dados atualizado com sucesso via Downloads: {excel_fat}")
        except Exception as e:
            print(f"❌ Erro ao ler e sincronizar o arquivo Excel na torre: {str(e)}")

    conn = get_db_connection()
    cursor = conn.cursor()
    metas_db = {}
    try:
        cursor.execute("SELECT data, valor_meta FROM metas_diarias WHERE data BETWEEN ? AND ?", 
                       (str(primeiro_dia), str(ultimo_dia)))
        for row in cursor.fetchall():
            chave_data = str(row['data']).strip()
            metas_db[chave_data] = float(row['valor_meta'])
    except Exception as e:
        print(f"⚠️ Aviso: Tabela de metas inacessível ou vazia: {str(e)}")
    finally:
        conn.close()

    faturamento_diario_real = {}
    total_financeiro_selecionado = 0.0
    contagem_notas_dia_selecionado = 0
    dados_auditoria_tela = []
    notas_unicas_expedidas = set()

    def converter_data_ultra(dt_input):
        if not dt_input or pd.isna(dt_input): return None
        if hasattr(dt_input, 'date'): return dt_input.date()
        dt_str = str(dt_input).strip().split()[0]
        if dt_str in ('', '-', 'nan', 'None', '-no value-'): return None
        formatos = ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d/%m/%y', '%m/%d/%Y')
        for fmt in formatos:
            try: return datetime.strptime(dt_str, fmt).date()
            except: pass
        return None

    if not df_excel.empty:
        col_emissao = df_excel.columns[0]
        col_nf = df_excel.columns[1]
        col_cliente = df_excel.columns[2]
        col_pedido = df_excel.columns[12]
        col_prod_desc = df_excel.columns[14]
        col_um = df_excel.columns[16]
        col_valor = df_excel.columns[19]

        df_excel[col_nf] = df_excel[col_nf].ffill()
        df_excel[col_emissao] = df_excel[col_emissao].ffill()
        df_excel[col_cliente] = df_excel[col_cliente].ffill()

        ultima_nf_valida = None
        ultima_data_valida = None
        ultimo_cliente_valido = None
        ultimo_pedido_valido = None

        for _, row in df_excel.iterrows():
            nf_bruta = str(row[col_nf]).split('.')[0].strip() if pd.notna(row[col_nf]) else ""
            if nf_bruta and nf_bruta not in ('nan', 'None', '-'):
                ultima_nf_valida = nf_bruta
            val_nf = ultima_nf_valida

            if not val_nf: 
                continue

            dt_convertida = converter_data_ultra(row[col_emissao])
            if dt_convertida:
                ultima_data_valida = dt_convertida
            dt_emissao_atual = ultima_data_valida

            if not dt_emissao_atual: 
                continue

            if pd.notna(row[col_cliente]) and str(row[col_cliente]).strip() not in ('', 'nan', 'None'):
                ultimo_cliente_valido = str(row[col_cliente]).strip()
            if pd.notna(row[col_pedido]) and str(row[col_pedido]).strip() not in ('', 'nan', 'None', '-No Value-'):
                ultimo_pedido_valido = str(row[col_pedido]).strip()

            val_um = str(row[col_um]).strip().upper() if pd.notna(row[col_um]) else ""
            desc_prod = str(row[col_prod_desc]).strip() if pd.notna(row[col_prod_desc]) else ""

            # 🛡️ Preservada a sua lógica mestre de validação de itens da outra máquina
            is_linha_totalizadora = (desc_prod == "" or desc_prod in ('nan', 'None', '-', '-No Value-'))
            is_item_real = not is_linha_totalizadora

            val_bruto = row[col_valor]
            val_float = 0.0
            if pd.notna(val_bruto):
                try:
                    if isinstance(val_bruto, (int, float)):
                        val_float = float(val_bruto)
                    else:
                        val_limpo = str(val_bruto).replace('R$', '').strip()
                        if '.' in val_limpo and ',' in val_limpo:
                            val_limpo = val_limpo.replace('.', '').replace(',', '.')
                        elif ',' in val_limpo:
                            val_limpo = val_limpo.replace(',', '.')
                        val_float = float(val_limpo)
                except:
                    val_float = 0.0

            if not is_item_real:
                if primeiro_dia <= dt_emissao_atual <= ultimo_dia:
                    data_s = str(dt_emissao_atual)
                    faturamento_diario_real[data_s] = faturamento_diario_real.get(data_s, 0.0) + val_float

                if dt_emissao_atual == dt_base:
                    total_financeiro_selecionado += val_float
                    contagem_notas_dia_selecionado += 1
                    
                    if val_nf in dict_expedicao:
                        notas_unicas_expedidas.add(val_nf)

                    dados_exp = dict_expedicao.get(val_nf, {"transportadora": "-"})
                    status_log = f"EXPEDIDO | 🚚 {dados_exp['transportadora']}" if dados_exp['transportadora'] != "-" else "NÃO EXPEDIDO"

                    dados_auditoria_tela.append({
                        "nf": val_nf,
                        "cliente": ultimo_cliente_valido if ultimo_cliente_valido else "-",
                        "produto": f"<b>TOTAL CONSOLIDADO DA NOTA</b> | {status_log}",
                        "valor_linha": 0.0,
                        "valor_total_nota": val_float,
                        "tipo_linha": "TOTALIZADOR"
                    })

                    dados_auditoria_tela.append({
                        "nf": "", "cliente": "", "produto": "",
                        "valor_linha": 0.0, "valor_total_nota": 0.0,
                        "tipo_linha": "DIVISOR"
                    })
            else:
                if dt_emissao_atual == dt_base:
                    dados_exp = dict_expedicao.get(val_nf, {
                        "data_exp": "Não Expedida", "transportadora": "-", "motorista": "-", "observacoes": ""
                    })

                    pedido_texto = f"Pedido: {ultimo_pedido_valido}" if ultimo_pedido_valido else "Item"
                    produto_detalhado = f"{desc_prod} ({pedido_texto}) | 🚚 {dados_exp['transportadora']} | Motorista: {dados_exp['motorista']}"
                    if dados_exp['observacoes']:
                        produto_detalhado += f" ({dados_exp['observacoes']})"

                    dados_auditoria_tela.append({
                        "nf": val_nf,
                        "cliente": ultimo_cliente_valido if ultimo_cliente_valido else "-",
                        "produto": produto_detalhado,
                        "valor_linha": val_float,
                        "valor_total_nota": 0.0,
                        "tipo_linha": "ITEM"
                    })

    tendencia_mensal = []
    acumulado_meta_ate_hoje = 0.0
    acumulado_real_ate_hoje = 0.0

    curr = primeiro_dia
    while curr <= ultimo_dia:
        data_s = str(curr).strip()
        realizado_dia = faturamento_diario_real.get(data_s, 0.0)
        meta_dia = metas_db.get(data_s, 0.0)
        
        if curr <= dt_base:
            acumulado_meta_ate_hoje += meta_dia
            acumulado_real_ate_hoje += realizado_dia

        tendencia_mensal.append({
            "data": data_s, "label": curr.strftime('%d/%m'),
            "realizado": round(realizado_dia, 2), "meta": round(meta_dia, 2)
        })
        curr += timedelta(days=1)

    falta_acumulado_mes = max(0, acumulado_meta_ate_hoje - acumulado_real_ate_hoje)
    qtd_expedidas_dia = len(notas_unicas_expedidas)
    qtd_pendentes_dia = max(0, contagem_notas_dia_selecionado - qtd_expedidas_dia)

    return {
        "resumo_dia": {
            "valor_faturado": round(total_financeiro_selecionado, 2),
            "qtd_notas": contagem_notas_dia_selecionado
        },
        "acumulado_mes": {
            "falta_no_mes": round(falta_acumulado_mes, 2)
        },
        "status_notas": {
            "entregues": 0, 
            "expedidas": qtd_expedidas_dia, 
            "nao_expedidas": qtd_pendentes_dia
        },
        "lead_times": {"pedido_faturamento": 0, "faturamento_expedicao": 0, "expedicao_entrega": 0},
        "tendencia_mensal": tendencia_mensal,
        "tabela_auditoria": dados_auditoria_tela
    }


@app.route('/api/listar_metas')
@login_requerido()
def listar_metas():
    data_filtro = request.args.get('data', '').strip()
    if data_filtro:
        try: dt_base = datetime.strptime(data_filtro, '%Y-%m-%d').date()
        except: dt_base = datetime.today().date()
    else:
        dt_base = datetime.today().date()

    primeiro_dia = dt_base.replace(day=1)
    ultimo_dia = (primeiro_dia + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    metas = {}
    try:
        cursor.execute("SELECT data, valor_meta FROM metas_diarias WHERE data BETWEEN ? AND ?", 
                       (str(primeiro_dia), str(ultimo_dia)))
        for row in cursor.fetchall():
            metas[str(row['data']).strip()] = float(row['valor_meta'])
    except Exception as e:
        print(f"❌ Erro ao listar metas: {str(e)}")
    finally:
        conn.close()

    return jsonify(metas)


@app.route('/api/salvar_meta', methods=['POST'])
@login_requerido()
def salvar_meta():
    dados = request.get_json()
    if not dados:
        return {"status": "erro", "mensagem": "Nenhum dado recebido"}, 400

    data_meta = dados.get('data')
    valor_meta = dados.get('valor') if dados.get('valor') is not None else dados.get('valor_meta')
    
    if not data_meta:
        return {"status": "erro", "mensagem": "Data nao informada"}, 400
    if valor_meta is None:
        return {"status": "erro", "mensagem": "Valor da meta nao informado"}, 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if database_adapter.is_sqlserver():
            cursor.execute("SELECT data FROM metas_diarias WHERE data = ?", (str(data_meta).strip(),))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE metas_diarias SET valor_meta = ? WHERE data = ?",
                    (float(valor_meta), str(data_meta).strip()),
                )
            else:
                cursor.execute(
                    "INSERT INTO metas_diarias (data, valor_meta) VALUES (?, ?)",
                    (str(data_meta).strip(), float(valor_meta)),
                )
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO metas_diarias (data, valor_meta) 
                VALUES (?, ?)
            """, (str(data_meta).strip(), float(valor_meta)))
        conn.commit()
        return {"status": "sucesso", "mensagem": "Meta salva com sucesso!"}
    except Exception as e:
        conn.rollback()
        return {"status": "erro", "mensagem": str(e)}, 500
    finally:
        conn.close()


# ============================================================
# RELATÓRIOS DO CORE OPERACIONAL E SISTEMAS DE FILTRO
# ============================================================

@app.route('/sistema_canhotos', methods=['GET'])
def sistema_canhotos():
    filtro = request.args.get('busca_cliente', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    if filtro:
        cursor.execute("SELECT * FROM canhotos WHERE cliente LIKE ? ORDER BY id DESC", (f'%{filtro}%',))
    else:
        cursor.execute("SELECT * FROM canhotos ORDER BY id DESC")

    rows = cursor.fetchall()
    conn.close()

    lista = [{
        'Cliente': r['cliente'], 'Nota Fiscal': r['nota_fiscal'],
        'Data Recebimento': r['data_recebimento'], 'Status': r['status'], 'Observações': r['observacoes']
    } for r in rows]
    return render_template('canhotos_sistema.html', canhotos=lista)


@app.route('/relatorio', methods=['GET'])
def relatorio():
    filtro_cliente = request.args.get('busca_cliente', '').strip()
    filtro_nf = request.args.get('busca_nf', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM ocorrencias WHERE 1=1"
    params = []

    if filtro_cliente:
        query += " AND LOWER(cliente) LIKE ?"
        params.append(f'%{filtro_cliente.lower()}%')
    if filtro_nf:
        query += " AND nota_fiscal LIKE ?"
        params.append(f'%{filtro_nf}%')

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    lista = [{
        'Cliente': r['cliente'], 'Nota Fiscal': r['nota_fiscal'],
        'Data': r['data'], 'Tratativa': r['tratativa'], 'Motivo': r['motivo']
    } for r in rows]
    return render_template('relatorio.html', ocorrencias=lista, filtro_cliente=filtro_cliente, filtro_nf=filtro_nf)


@app.route('/relatorio_coletas', methods=['GET'])
def relatorio_coletas():
    filtro_cliente = request.args.get('busca_cliente', '').strip()
    filtro_nf = request.args.get('busca_nf', '').strip()
    filtro_transp = request.args.get('busca_transp', '').strip()
    filtro_data = request.args.get('busca_data', '').strip()
    filtro_apenas_pendentes = request.args.get('apenas_pendentes', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM coletas WHERE status LIKE '%Pendente%'")
    pendentes = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM coletas WHERE status LIKE '%Efetuada%'")
    efetuadas = cursor.fetchone()[0] or 0

    query = "SELECT * FROM coletas WHERE 1=1"
    params = []

    if filtro_cliente:
        query += " AND LOWER(cliente) LIKE ?"
        params.append(f'%{filtro_cliente.lower()}%')
    if filtro_nf:
        query += " AND nota_fiscal LIKE ?"
        params.append(f'%{filtro_nf}%')
    if filtro_transp:
        query += " AND LOWER(transportadora) LIKE ?"
        params.append(f'%{filtro_transp.lower()}%')
    if filtro_data:
        try:
            data_convertida = datetime.strptime(filtro_data, '%Y-%m-%d').strftime('%d/%m/%Y')
            query += " AND data_solicitacao LIKE ?"
            params.append(f'%{data_convertida}%')
        except Exception:
            query += " AND data_solicitacao LIKE ?"
            params.append(f'%{filtro_data}%')

    if filtro_apenas_pendentes == 'on':
        query += " AND status LIKE '%Pendente%'"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    lista = []
    hoje = datetime.now().date()
    texto_email_linhas = []

    for r in rows:
        status_atual = r['status']
        data_solic_str = r['data_solicitacao']
        alerta_dias, classe_alerta = "Data sem formato", ""
        
        try:
            data_coleta = datetime.strptime(data_solic_str, '%d/%m/%Y').date() if "/" in data_solic_str else datetime.strptime(data_solic_str, '%Y-%m-%d').date()
            diferenca = (data_coleta - hoje).days
            
            if "Pendente" in status_atual:
                if diferenca > 0:
                    alerta_dias = f"Faltam {diferenca} dias"
                    classe_alerta = "alerta-futuro"
                elif diferenca == 0:
                    alerta_dias = "🚨 É HOJE!"
                    classe_alerta = "alerta-hoje"
                else:
                    alerta_dias = f"Atrasado há {abs(diferenca)} dias"
                    classe_alerta = "alerta-atrasado"
            else:
                alerta_dias = "Concluído"
                classe_alerta = "alerta-concluido"
        except Exception:
            pass

        item = {
            'Cliente': r['cliente'], 'Nota Fiscal': r['nota_fiscal'], 'Transportadora': r['transportadora'],
            'Data Solicitação': r['data_solicitacao'], 'Status': status_atual, 'AlertaDias': alerta_dias, 'ClasseAlerta': classe_alerta
        }
        lista.append(item)
        if "Pendente" in status_atual:
            texto_email_linhas.append(f"• Cliente: {item['Cliente']} | NF: {item['Nota Fiscal']} | Transp: {item['Transportadora']} | Data Programada: {item['Data Solicitação']} ({alerta_dias})")

    corpo_email_padrao = "Prezados,\n\nSegue a lista de coletas pendentes update:\n\n"
    corpo_email_padrao += "\n".join(texto_email_linhas) if texto_email_linhas else "Nenhuma coleta pendente encontrada para os filtros selecionados."
    corpo_email_padrao += "\n\nFicamos no aguardo do retorno operacional.\n\nAtenciosamente,"

    return render_template('relatorio_coletas.html', coletas=lista, filtro_cliente=filtro_cliente, filtro_nf=filtro_nf,
                           filtro_transp=filtro_transp, filtro_data=filtro_data, filtro_apenas_pendentes=filtro_apenas_pendentes,
                           pendentes=pendentes, efetuadas=efetuadas, static_mail_data=corpo_email_padrao)

# 🟢 DUPLO MAPEAMENTO: Aceita tanto o link novo quanto o antigo mapeado nos seus botões
@app.route('/registrar_coleta')
@app.route('/formulario_coleta')
def abrir_formulario_registro_coleta():
    # Puxa a lista viva de transportadoras registradas no SQLite
    lista_transp = ler_transportadoras_db()
    return render_template('registrar_coleta.html', lista_transportadoras=lista_transp)

# ============================================================
# 📡 MOTORES DE EXTRAÇÃO AUTOMÁTICA NOMUS ERP (APIs NUVEM)
# ============================================================

# ============================================================
# 📡 MOTORES DE EXTRAÇÃO AUTOMÁTICA NOMUS ERP (APIs NUVEM)
# ============================================================

import io
import sqlite3
import requests
import pandas as pd
from flask import Flask, render_template, request, session, redirect, jsonify

# ============================================================
# 📡 MOTORES DE EXTRAÇÃO AUTOMÁTICA NOMUS ERP (APIs NUVEM)
# ============================================================

# ============================================================
# 📡 MOTORES DE EXTRAÇÃO RECALIBRADOS NOMUS ERP (APIs NUVEM)
# ============================================================

# ============================================================
# 📡 MOTORES DE EXTRAÇÃO RECALIBRADOS NOMUS ERP (APIs NUVEM)
# ============================================================

# ============================================================
# 📊 ROTA MESTRE RESTAURADA: LEITURA LOCAL E CONCILIAÇÃO
# ============================================================

@app.route('/relatorio_faturamento', methods=['GET'])
def relatorio_faturamento():
    if 'usuario_id' not in session:
        return redirect('/login')

    filtro_inicio = request.args.get('data_inicio', '').strip()
    filtro_fim = request.args.get('data_fim', '').strip()
    filtro_nf = request.args.get('busca_nf', '').strip()
    filtro_cliente = request.args.get('busca_cliente', '').strip()
    filtro_transp = request.args.get('busca_transp', '').strip()
    busca_status = request.args.get('busca_status', '').strip()
    
    pagina = request.args.get('page', 1, type=int)
    registros_por_pagina = 100
    offset = (pagina - 1) * registros_por_pagina

    # 📥 1. PROCURA E PROCESSA O ARQUIVO LOCAL DE FATURAMENTO (só se o arquivo mudou)
    excel_fat = obter_planilha_faturamento_conciliacao()
    if excel_fat:
        try:
            importar_faturamento_se_necessario(excel_fat)
            print(f"✔️ [CONCILIAÇÃO LOCAL] Banco sincronizado com: {excel_fat}")
        except Exception as e:
            print(f"⚠️ Aviso de sincronia faturamento local: {e}")

    # 📥 2. PROCURA E PROCESSA O ARQUIVO DE EXPEDIÇÃO (manual do cliente ou automático no servidor)
    dict_expedidas_relatorio = {}
    excel_exp = obter_planilha_expedicao_conciliacao()
    fonte_exp = 'manual' if excel_exp == ARQUIVO_EXPEDICAO_MANUAL else 'automatica'
    if excel_exp:
        try:
            dict_expedidas_relatorio = mapear_dict_expedicao_de_excel(excel_exp)
            print(f"✔️ [CONCILIAÇÃO] Planilha de expedição ({fonte_exp}) mapeada: {excel_exp}")
        except Exception as e:
            print(f"❌ Erro ao mapear arquivo de expedição: {e}")

    dict_wms_relatorio = {'por_nf': {}, 'por_codigo': {}, 'arquivo': None}
    excel_wms = obter_planilha_wms_conciliacao()
    fonte_wms = 'manual' if excel_wms == ARQUIVO_WMS_MANUAL else 'automatica'
    if excel_wms:
        try:
            dict_wms_relatorio = mapear_posicoes_wms_de_excel(excel_wms)
            print(f"✔️ [CONCILIAÇÃO WMS] Template wms_apontamento ({fonte_wms}) mapeado: {excel_wms}")
        except Exception as e:
            print(f"⚠️ Erro ao mapear WMS apontamento: {e}")

    # 3. CONSULTA DOS DADOS CONSOLIDADOS NO SQLITE LOCAL
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM faturamento")
        total_geral_faturadas = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM entregas_efetuadas")
        total_geral_entregues_db = cursor.fetchone()[0] or 0

        where_clauses = ["1=1"]
        params = []

        if filtro_cliente:
            where_clauses.append("f.cliente LIKE ?")
            params.append(f'%{filtro_cliente}%')
        if filtro_nf:
            where_clauses.append("f.nf LIKE ?")
            params.append(f'%{filtro_nf}%')
        if filtro_transp:
            where_clauses.append("f.transportadora LIKE ?")
            params.append(f'%{filtro_transp}%')
        if filtro_inicio:
            where_clauses.append("f.emissao >= ?")
            params.append(filtro_inicio)
        if filtro_fim:
            where_clauses.append("f.emissao <= ?")
            params.append(filtro_fim)

        where_str = " AND ".join(where_clauses)

        group_by_nf = "" if database_adapter.is_sqlserver() else "GROUP BY f.nf"
        query_dados_total = f"""
            SELECT 
                f.nf AS [Nota Fiscal], f.emissao AS [Emissão], f.cliente AS [Cliente], 
                f.endereco AS [Endereço], f.municipio AS [Município], f.uf AS [UF], f.cep AS [CEP], 
                f.transportadora AS [Transportadora], f.modalidade AS [Modalidade], f.volumes AS [Volumes], 
                f.especie AS [Espécie], f.peso_bruto_nf AS [Peso Bruto], f.pedido AS [Pedido], 
                f.valor_total_nf AS [Valor Total], e.data_entrega AS [Data Entrega], 
                e.recebedor AS [Recebedor], e.assinatura AS [Assinatura / Obs] 
            FROM faturamento f 
            LEFT JOIN entregas_efetuadas e ON f.nf = e.nota_fiscal 
            WHERE {where_str} 
            {group_by_nf}
            ORDER BY f.nf DESC
        """
        
        cursor.execute(query_dados_total, params)
        rows_completas = cursor.fetchall()

        itens_por_nf = {}
        cursor.execute("SELECT nf, codigo_item FROM faturamento_itens WHERE codigo_item IS NOT NULL AND codigo_item <> ''")
        for row_item in cursor.fetchall():
            nf_item = _limpar_numero_nf(row_item['nf'])
            codigo_item = _limpar_codigo_material(row_item['codigo_item'])
            if nf_item and codigo_item:
                itens_por_nf.setdefault(nf_item, set()).add(codigo_item)
        itens_por_nf = {nf: sorted(codigos) for nf, codigos in itens_por_nf.items()}
        conn.close()
    except Exception as db_error:
        print(f"❌ Erro Crítico de Banco de Dados: {db_error}")
        return f"Erro interno no Banco de Dados: {db_error}", 500

    # 4. PROCESSAMENTO DOS STATUS E HIGIENIZAÇÃO DE VALORES (CRUZAMENTO TRIPLO)
    dados_filtrados_com_status = []
    total_expedidas_filtro = 0
    total_nao_exp_filtro = 0
    valor_total_filtro = 0.0

    for r in rows_completas:
        item = dict(r)
        nf_str = _limpar_numero_nf(item['Nota Fiscal'])
        item['Nota Fiscal'] = nf_str
        
        val_raw = str(item['Valor Total']).replace('R$', '').strip()
        val_limpo = val_raw.replace('.', '').replace(',', '.') if ',' in val_raw and '.' in val_raw else val_raw.replace(',', '.') if ',' in val_raw else val_raw
        try: val_float = float(val_limpo)
        except Exception: val_float = 0.0

        # Cruza com o dicionário gerado a partir do arquivo de expedição local
        info_exp_combinada = dict_expedidas_relatorio.get(nf_str, None)

        if item.get('Data Entrega') and item['Data Entrega'] not in ('', '-', None):
            status_final = 'ENTREGUE'
            item['DW PosiÃ§Ã£o WMS'] = 'ENTREGUE'
            item['Data Expedição'] = info_exp_combinada['data_expedicao'] if info_exp_combinada else "-"
        elif info_exp_combinada is not None:
            status_final = 'EXPEDIDO'
            item['DW PosiÃ§Ã£o WMS'] = 'EXPEDIDA'
            total_expedidas_filtro += 1
            item['Data Expedição'] = info_exp_combinada['data_expedicao']
        else:
            status_final = 'NÃO EXPEDIDO'
            total_nao_exp_filtro += 1
            item['DW PosiÃ§Ã£o WMS'] = _posicao_wms_para_nf(nf_str, dict_wms_relatorio, itens_por_nf)
            item['Data Expedição'] = "-"

        item['STATUS EXPEDIÇÃO'] = status_final

        if status_final == 'ENTREGUE':
            item['DW_POSICAO_WMS'] = 'ENTREGUE'
        elif status_final == 'EXPEDIDO':
            item['DW_POSICAO_WMS'] = 'EXPEDIDA'
        else:
            item['DW_POSICAO_WMS'] = _posicao_wms_para_nf(nf_str, dict_wms_relatorio, itens_por_nf)

        if busca_status and status_final != busca_status:
            continue
            
        valor_total_filtro += val_float
        dados_filtrados_com_status.append(item)

    total_faturadas_filtro = len(dados_filtrados_com_status)
    financeiro_filtrado = round(valor_total_filtro, 2)
    
    total_geral_movimentadas = total_geral_entregues_db
    total_geral_em_aberto_recalculado = max(0, total_geral_faturadas - total_geral_movimentadas)
    taxa_eficiencia = round((total_geral_movimentadas / total_geral_faturadas * 100), 1) if total_geral_faturadas > 0 else 0.0

    dados_lista_paginada = dados_filtrados_com_status[offset : offset + registros_por_pagina]

    colunas = [
        'Nota Fiscal', 'Emissão', 'Cliente', 'Endereço', 'Município', 'UF', 'CEP',
        'Transportadora', 'Modalidade', 'Volumes', 'Espécie', 'Peso Bruto', 'Pedido',
        'Valor Total', 'STATUS EXPEDIÇÃO', 'Data Expedição', 'Data Entrega', 'Recebedor', 'Assinatura / Obs'
    ]

    if 'DW PosiÃ§Ã£o WMS' not in colunas:
        colunas.insert(colunas.index('Valor Total') + 1, 'DW PosiÃ§Ã£o WMS')

    if 'DW_POSICAO_WMS' not in colunas:
        colunas.insert(colunas.index('Valor Total') + 1, 'DW_POSICAO_WMS')

    return render_template(
        'relatorio_faturamento.html', dados=dados_lista_paginada, colunas=colunas,
        filtro_nf=filtro_nf, filtro_cliente=filtro_cliente, filtro_transp=filtro_transp,
        busca_status=busca_status, data_inicio=filtro_inicio, data_fim=filtro_fim,
        total_faturadas=total_geral_faturadas, total_expedidas=total_geral_movimentadas,
        total_em_aberto=total_geral_em_aberto_recalculado, taxa_eficiencia=taxa_eficiencia,
        total_faturadas_filtro=total_faturadas_filtro, total_expedidas_filtro=total_expedidas_filtro,
        total_em_aberto_filtro=total_nao_exp_filtro,
        financeiro_filtrado=f"R$ {financeiro_filtrado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        page=pagina, tem_mais=(len(dados_filtrados_com_status) > offset + registros_por_pagina), erro=None,
        arquivo_fat_auto=os.path.basename(excel_fat) if excel_fat else None,
        arquivo_exp_ativo=os.path.basename(excel_exp) if excel_exp else None,
        arquivo_wms_ativo=os.path.basename(excel_wms) if excel_wms else None,
        fonte_expedicao=fonte_exp if excel_exp else None,
        fonte_wms=fonte_wms if excel_wms else None,
        atualizacao_manual=info_ultima_atualizacao_manual(),
    )


@app.route('/teste_sqlserver_faturamento', methods=['GET'])
@login_requerido()
def teste_sqlserver_faturamento():
    """Tela isolada para medir consulta direta no SQL Server sobre a base de faturamento."""
    return render_template(
        'teste_sqlserver_faturamento.html',
        sqlserver_ativo=database_adapter.is_sqlserver(),
        backend_info=database_adapter.describe_backend(),
    )


@app.route('/api/teste_sqlserver_faturamento', methods=['GET'])
@login_requerido()
def api_teste_sqlserver_faturamento():
    """Consulta 100% SQL Server, sem Excel/SQLite, para comparar performance."""
    import time

    if not database_adapter.is_sqlserver():
        return jsonify({
            "status": "erro",
            "mensagem": "Ative DB_BACKEND=sqlserver para executar este teste direto no SQL Server."
        }), 400

    nf = request.args.get('nf', '').strip()
    cliente = request.args.get('cliente', '').strip()
    transportadora = request.args.get('transportadora', '').strip()
    emissao_inicio = request.args.get('emissao_inicio', '').strip()
    emissao_fim = request.args.get('emissao_fim', '').strip()

    try:
        limite = int(request.args.get('limite', 200))
    except Exception:
        limite = 200
    limite = max(10, min(limite, 1000))

    where = ["1=1"]
    params = []
    if nf:
        where.append("f.nf LIKE ?")
        params.append(f"%{nf}%")
    if cliente:
        where.append("f.cliente LIKE ?")
        params.append(f"%{cliente}%")
    if transportadora:
        where.append("f.transportadora LIKE ?")
        params.append(f"%{transportadora}%")
    if emissao_inicio:
        where.append("f.emissao >= ?")
        params.append(emissao_inicio)
    if emissao_fim:
        where.append("f.emissao <= ?")
        params.append(emissao_fim)

    where_sql = " AND ".join(where)
    conn = get_db_connection()
    cursor = conn.cursor()
    inicio = time.perf_counter()

    try:
        cursor.execute(f"SELECT COUNT_BIG(*) AS total FROM faturamento f WHERE {where_sql}", tuple(params))
        total_filtrado = int(cursor.fetchone()["total"] or 0)

        cursor.execute(f"""
            SELECT TOP ({limite})
                f.nf,
                f.emissao,
                f.cliente,
                f.municipio,
                f.uf,
                f.cep,
                f.transportadora,
                f.modalidade,
                f.volumes,
                f.peso_bruto_nf,
                f.pedido,
                f.valor_total_nf,
                e.data_entrega,
                e.recebedor
            FROM faturamento f
            LEFT JOIN entregas_efetuadas e ON e.nota_fiscal = f.nf
            WHERE {where_sql}
            ORDER BY f.nf DESC
        """, tuple(params))
        rows = cursor.fetchall()
    finally:
        conn.close()

    tempo_ms = round((time.perf_counter() - inicio) * 1000, 2)
    dados = [{
        "nf": r["nf"],
        "emissao": r["emissao"],
        "cliente": r["cliente"],
        "municipio": r["municipio"],
        "uf": r["uf"],
        "cep": r["cep"],
        "transportadora": r["transportadora"],
        "modalidade": r["modalidade"],
        "volumes": r["volumes"],
        "peso_bruto_nf": r["peso_bruto_nf"],
        "pedido": r["pedido"],
        "valor_total_nf": r["valor_total_nf"],
        "data_entrega": r["data_entrega"],
        "recebedor": r["recebedor"],
    } for r in rows]

    return jsonify({
        "status": "sucesso",
        "backend": database_adapter.describe_backend(),
        "tempo_ms": tempo_ms,
        "total_filtrado": total_filtrado,
        "limite": limite,
        "retornados": len(dados),
        "dados": dados,
    })


@app.route('/api/importar_faturamento_manual', methods=['POST'])
@login_requerido()
def api_importar_faturamento_manual():
    """Recebe planilha do navegador do cliente (ex.: Downloads da máquina que acessa via IP)."""
    arquivo = request.files.get('arquivo')
    if not arquivo or not arquivo.filename:
        return jsonify({"status": "erro", "mensagem": "Selecione um arquivo Excel de faturamento."}), 400
    if not _validar_extensao_planilha(arquivo.filename):
        return jsonify({"status": "erro", "mensagem": "Formato inválido. Use .xlsx ou .xls."}), 400

    garantir_pasta_uploads_manual()
    nome_origem = arquivo.filename
    arquivo.save(ARQUIVO_FATURAMENTO_MANUAL)
    try:
        importar_faturamento_para_sqlite(ARQUIVO_FATURAMENTO_MANUAL)
        invalidar_cache_faturamento()
        _cache_importacoes['faturamento'] = (ARQUIVO_FATURAMENTO_MANUAL, os.path.getmtime(ARQUIVO_FATURAMENTO_MANUAL))
        registrar_log_operacional("IMPORTAÇÃO MANUAL FATURAMENTO", f"Arquivo: {nome_origem}")
        return jsonify({
            "status": "sucesso",
            "mensagem": f"Base de faturamento atualizada com o arquivo «{nome_origem}».",
            "arquivo": nome_origem,
        })
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Falha ao importar: {e}"}), 500


@app.route('/api/importar_expedicao_manual', methods=['POST'])
@login_requerido()
def api_importar_expedicao_manual():
    """Recebe planilha de expedição do navegador do cliente para conciliação."""
    arquivo = request.files.get('arquivo')
    if not arquivo or not arquivo.filename:
        return jsonify({"status": "erro", "mensagem": "Selecione um arquivo Excel de expedição."}), 400
    if not _validar_extensao_planilha(arquivo.filename):
        return jsonify({"status": "erro", "mensagem": "Formato inválido. Use .xlsx ou .xls."}), 400

    garantir_pasta_uploads_manual()
    nome_origem = arquivo.filename
    try:
        arquivo.save(ARQUIVO_EXPEDICAO_MANUAL)
        df_bruto = pd.read_excel(ARQUIVO_EXPEDICAO_MANUAL)
        df_tratado, col_nf, _ = normalizar_dataframe_expedicao(df_bruto)
        df_tratado[col_nf] = df_tratado[col_nf].apply(_limpar_numero_nf)
        df_tratado.to_excel(ARQUIVO_EXPEDICAO_MANUAL, index=False)
        invalidar_cache_expedicao()
        total_nfs = int(df_tratado[col_nf].astype(str).str.strip().ne('').sum())
        registrar_log_operacional("IMPORTAÇÃO MANUAL EXPEDIÇÃO", f"Arquivo: {nome_origem} ({total_nfs} NFs)")
        return jsonify({
            "status": "sucesso",
            "mensagem": f"Planilha «{nome_origem}» importada com {total_nfs} nota(s). Atualizando painel…",
            "arquivo": nome_origem,
            "total_nfs": total_nfs,
        })
    except Exception as e:
        if os.path.exists(ARQUIVO_EXPEDICAO_MANUAL):
            try:
                os.remove(ARQUIVO_EXPEDICAO_MANUAL)
            except OSError:
                pass
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


# ============================================================
# 🔍 ENDPOINTS DE INSPEÇÃO DIRETA DE APIs (GRADE DE AUDITORIA)
# ============================================================

@app.route('/api/importar_wms_manual', methods=['POST'])
@login_requerido()
def api_importar_wms_manual():
    """Recebe o template wms_apontamento do navegador para exibir posicao no faturamento."""
    arquivo = request.files.get('arquivo')
    if not arquivo or not arquivo.filename:
        return jsonify({"status": "erro", "mensagem": "Selecione o template wms_apontamento."}), 400
    if not _validar_extensao_planilha(arquivo.filename):
        return jsonify({"status": "erro", "mensagem": "Formato invalido. Use .xlsx ou .xls."}), 400

    garantir_pasta_uploads_manual()
    nome_origem = arquivo.filename
    try:
        arquivo.save(ARQUIVO_WMS_MANUAL)
        invalidar_cache_wms()
        mapa = mapear_posicoes_wms_de_excel(ARQUIVO_WMS_MANUAL)
        total_refs = len(mapa.get('por_nf', {})) + len(mapa.get('por_codigo', {}))
        registrar_log_operacional("IMPORTACAO MANUAL WMS", f"Arquivo: {nome_origem} ({total_refs} referencias)")
        return jsonify({
            "status": "sucesso",
            "mensagem": f"Template WMS «{nome_origem}» importado com {total_refs} referencia(s).",
            "arquivo": nome_origem,
            "total_referencias": total_refs,
        })
    except Exception as e:
        if os.path.exists(ARQUIVO_WMS_MANUAL):
            try:
                os.remove(ARQUIVO_WMS_MANUAL)
            except OSError:
                pass
        invalidar_cache_wms()
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route('/auditar_apis_nomus', methods=['GET'])
def auditar_apis_nomus():
    if 'usuario_id' not in session:
        return redirect('/login')
    return render_template('auditar_apis_nomus.html')

@app.route('/api/dados_brutos_faturamento')
@login_requerido()
def dados_brutos_faturamento():
    df = extrair_faturamento_nomus()
    if df is not None:
        colunas = list(df.columns)
        linhas = df.head(50).fillna('-').to_dict(orient='records')
        return jsonify({"status": "sucesso", "colunas": colunas, "dados": linhas})
    return jsonify({"status": "erro", "mensagem": "Falha na leitura da API 1 (Faturamento)"})

@app.route('/api/dados_brutos_expedicao')
@login_requerido()
def dados_brutos_expedicao():
    df = extrair_expedicao_nomus()
    if df is not None:
        colunas = list(df.columns)
        linhas = df.head(50).fillna('-').to_dict(orient='records')
        return jsonify({"status": "sucesso", "colunas": colunas, "dados": linhas})
    return jsonify({"status": "erro", "mensagem": "Falha na leitura da API 2 (Expedição)"})


@app.route('/relatorio_transportadoras', methods=['GET'])
def relatorio_transportadoras():
    filtro = request.args.get('busca_transp', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    if filtro:
        cursor.execute("SELECT * FROM transportadoras WHERE LOWER(name) LIKE ? ORDER BY name ASC", (f'%{filtro.lower()}%',))
    else:
        cursor.execute("SELECT * FROM transportadoras ORDER BY name ASC")

    rows = cursor.fetchall()
    conn.close()

    lista = [{'Transportadora': r['name'], 'Telefone': r['telefone'], 'Responsável': r['responsavel']} for r in rows]
    return render_template('relatorio_transportadoras.html', transportadoras=lista, filtro_transp=filtro)


@app.route('/relatorio_expedicao', methods=['GET'])
def relatorio_expedicao():
    if 'usuario_id' not in session:
        return redirect('/login')

    filtro_inicio = request.args.get('data_inicio', '').strip()
    filtro_fim = request.args.get('data_fim', '').strip()
    filtro_nf = request.args.get('busca_nf', '').strip()
    filtro_cliente = request.args.get('busca_cliente', '').strip()
    filtro_transp = request.args.get('busca_transp', '').strip()

    colunas, dados_lista, msg_erro = [], [], None
    excel_exp_auto = buscar_ultima_expedicao()
    excel_exp = obter_planilha_expedicao_conciliacao()
    fonte_exp = None
    if excel_exp:
        fonte_exp = 'manual' if excel_exp == ARQUIVO_EXPEDICAO_MANUAL else 'automatica'

    ctx_base = dict(
        filtro_nf=filtro_nf, filtro_cliente=filtro_cliente, filtro_transp=filtro_transp,
        data_inicio=filtro_inicio, data_fim=filtro_fim,
        arquivo_exp_auto=os.path.basename(excel_exp_auto) if excel_exp_auto else None,
        arquivo_exp_ativo=os.path.basename(excel_exp) if excel_exp else None,
        fonte_expedicao=fonte_exp,
        atualizacao_manual=info_ultima_atualizacao_manual(),
    )

    if not excel_exp:
        return render_template(
            'relatorio_expedicao.html',
            dados=[], colunas=[],
            erro="Nenhum arquivo de expedição ativo. Use a importação manual abaixo (pasta Downloads deste computador) ou coloque o arquivo no servidor.",
            **ctx_base,
        )

    try:
        df, col_nf, col_data, cols = carregar_dataframe_expedicao(excel_exp)
        col_cli = next((c for c in cols if 'clie' in str(c).lower() or 'raz' in str(c).lower() or 'model' in str(c).lower()), cols[min(2, len(cols) - 1)])
        col_transp = next((c for c in cols if 'transp' in str(c).lower()), cols[min(3, len(cols) - 1)])

        if col_data and filtro_inicio and filtro_fim:
            df[col_data] = pd.to_datetime(df[col_data], errors='coerce')
            df = df[(df[col_data] >= pd.to_datetime(filtro_inicio)) & (df[col_data] <= pd.to_datetime(filtro_fim))]
            df[col_data] = df[col_data].dt.strftime('%d/%m/%Y')
        elif col_data:
            try: df[col_data] = pd.to_datetime(df[col_data], errors='coerce').dt.strftime('%d/%m/%Y')
            except: pass

        if filtro_nf:
            df = df[df[col_nf].str.contains(filtro_nf, case=False, na=False)]
        if filtro_cliente and col_cli:
            df = df[df[col_cli].astype(str).str.contains(filtro_cliente, case=False, na=False)]
        if filtro_transp and col_transp:
            df = df[df[col_transp].astype(str).str.contains(filtro_transp, case=False, na=False)]

        df = df.fillna("-")
        colunas = df.columns.tolist()
        dados_lista = df.to_dict(orient='records')
        print(f"➔ [DEBUG EXPEDIÇÃO] {len(dados_lista)} linhas processadas ({fonte_exp}).")

    except Exception as e:
        msg_erro = f"Erro crítico no alinhamento das colunas: {str(e)}"
        print(f"❌ {msg_erro}")

    return render_template(
        'relatorio_expedicao.html', dados=dados_lista, colunas=colunas,
        erro=msg_erro, **ctx_base,
    )

# ============================================================
# SALVAR ENTRADAS DE FORMULÁRIOS E APOIO DE NEGÓCIO
# ============================================================

@app.route('/salvar', methods=['POST'])
@login_requerido()
def salvar():
    cliente = request.form.get('cliente', '').strip()
    nf = request.form.get('nota_fiscal', '').strip()
    data = request.form.get('data', '').strip()
    tratativa = request.form.get('tratativa', '').strip()
    motivo = request.form.get('item_word', '').strip()
    observacao = request.form.get('observacao', '').strip()  # 📝 Captura o novo campo de digitação livre

    try: 
        data_f = datetime.strptime(data, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception: 
        data_f = data

    # Normaliza o número da nota tirando espaços e zeros à esquerda para o match perfeito
    nf_limpa = nf.lstrip('0').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Mantém a gravação original na tabela de ocorrências
    cursor.execute("INSERT INTO ocorrencias (cliente, nota_fiscal, data, tratativa, motivo) VALUES (?, ?, ?, ?, ?)",
                   (cliente, nf, data_f, tratativa, motivo))
    
    # 🚀 2. INSERE OU ATUALIZA A OBSERVAÇÃO NA TABELA DE FATURAMENTO CRUZADO (entregas_efetuadas)
    # É essa tabela que abastece a última coluna do seu painel ("Assinatura / Obs")
    if observacao:
        upsert_entrega_efetuada(
            cursor,
            nf_limpa,
            data_f,
            f"TRATATIVA: {tratativa.upper()}",
            observacao,
        )

    conn.commit()
    conn.close()

    # Mantém o seu retorno original abrindo a tela de sucesso com o texto gerado
    texto = f"Prezados,\n\nNova ocorrência registrada.\n\n• Cliente: {cliente}\n• NF: {nf}\n• Data: {data_f}\n• Motivo: {motivo}\n• Observação: {observacao}"
    return render_template('sucesso.html', texto_notificacao=texto)


@app.route('/salvar_coleta', methods=['POST'])
@login_requerido()
def salvar_coleta():
    cliente = request.form.get('cliente', '').strip()
    nf = request.form.get('nota_fiscal', '').strip()
    transp = request.form.get('transportadora', '').strip()
    data = request.form.get('data', '').strip()
    status = request.form.get('status', '').strip()

    try: data_f = datetime.strptime(data, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception: data_f = data

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO coletas (cliente, nota_fiscal, transportadora, data_solicitacao, status) VALUES (?, ?, ?, ?, ?)",
                   (cliente, nf, transp, data_f, status))
    conn.commit()
    
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM coletas ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    lista = []
    texto_email_linhas = []
    pendentes, efetuadas = 0, 0

    for r in rows:
        lista.append({'cliente': r['cliente'], 'nota_fiscal': r['nota_fiscal'], 'transportadora': r['transportadora'], 'data_solicitacao': r['data_solicitacao'], 'status': r['status']})
        if r['status'].lower() == 'pendente':
            pendentes += 1
            texto_email_linhas.append(f"• NF: {r['nota_fiscal']} | Cliente: {r['cliente']} | Transp: {r['transportadora']}")
        else:
            efetuadas += 1

    corpo_email_padrao = "Prezados,\n\nSegue a lista de coletas pendentes atualizada:\n\n"
    corpo_email_padrao += "\n".join(texto_email_linhas) if texto_email_linhas else "Nenhuma coleta pendente encontrada."
    corpo_email_padrao += "\n\nFicamos no aguardo do retorno operacional.\n\nAtenciosamente,"

    return render_template('relatorio_coletas.html', coletas=lista, filtro_cliente="", filtro_nf="", filtro_transp="", filtro_data="", filtro_apenas_pendentes="",
                           pendentes=pendentes, efetuadas=efetuadas, static_mail_data=corpo_email_padrao)


@app.route('/salvar_transportadora', methods=['POST'])
@login_requerido()
def salvar_transportadora():
    nome = request.form.get('nome_transportadora', '').strip()
    tel = request.form.get('telefone_transportadora', '').strip()
    resp = request.form.get('responsavel_transportadora', '').strip()

    if not nome: return redirect('/relatorio_transportadoras')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO transportadoras (name, telephone, responsavel) VALUES (?, ?, ?)", (nome, tel, resp))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect('/relatorio_transportadoras')


@app.route('/salvar_entrega_faturamento', methods=['POST'])
@login_requerido()
def salvar_entrega_faturamento():
    nf = request.form.get('entrega_nf', '').strip()
    data = request.form.get('entrega_data', '').strip()

    try: data_f = datetime.strptime(data, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception: data_f = data

    conn = get_db_connection()
    cursor = conn.cursor()
    upsert_entrega_efetuada(cursor, nf, data_f)
    conn.commit()
    conn.close()
    return redirect('/relatorio_faturamento')


@app.route('/buscar_nf')
def buscar_nf():
    nf = request.args.get("nf", "").strip()
    if not nf: return {"erro": "NF não informada"}, 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM faturamento WHERE nf = ?", (nf,))
    cab = cur.fetchone()

    if not cab:
        conn.close()
        return {"erro": "NF não encontrada"}, 404

    cur.execute("SELECT codigo_item, descricao_item, qtde, um, peso_unitario, peso_total FROM faturamento_itens WHERE nf = ?", (nf,))
    itens = cur.fetchall()
    conn.close()

    return {
        "nf": cab["nf"], "emissao": cab["emissao"], "cliente": cab["cliente"], "endereco": cab["endereco"],
        "municipio": cab["municipio"], "uf": cab["uf"], "cep": cab["cep"], "transportadora": cab["transportadora"],
        "modalidade": cab["modalidade"], "volumes": cab["volumes"], "especie": cab["especie"],
        "peso_bruto_nf": cab["peso_bruto_nf"], "pedido": cab["pedido"], "valor_total_nf": cab["valor_total_nf"],
        "itens": [{"codigo": i["codigo_item"], "descricao": i["descricao_item"], "qtde": i["qtde"], "um": i["um"], "peso_unitario": i["peso_unitario"], "peso_total": i["peso_total"]} for i in itens]
    }


@app.route('/salvar_entrega_confirmada', methods=['POST'])
@login_requerido()
def salvar_entrega_confirmada():
    nf = request.form.get('nf_confirmada', '').strip()
    data = request.form.get('data_confirmada', '').strip()
    recebedor = request.form.get('recebedor_confirmado', '').strip()

    try: data_f = datetime.strptime(data, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception: data_f = data

    conn = get_db_connection()
    cursor = conn.cursor()
    upsert_entrega_efetuada(cursor, nf, data_f, recebedor)
    conn.commit()
    conn.close()
    return redirect('/relatorio_faturamento')

@app.route('/api/indicadores_expedicao')
def api_indicadores_expedicao():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 📊 Conta as notas por modalidade (Nosso Carro, FOB, Retira)
    # Ajuste os nomes 'NOSSO CARRO', 'FOB' etc conforme aparecem na sua planilha
    query = """
        SELECT modalidade, COUNT(*) as qtd 
        FROM faturamento 
        GROUP BY modalidade
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    # Transforma em um formato que o gráfico entende
    dados = {row['modalidade']: row['qtd'] for row in rows}
    return jsonify(dados)


@app.route('/baixa_entrega_mobile', methods=['GET', 'POST'])
def baixa_entrega_mobile():
    if request.method == 'POST':
        nf = request.form.get('nf', '').strip()
        data = request.form.get('data_entrega', '').strip()
        recebedor = request.form.get('recebedor', '').strip()
        assinatura = request.form.get('assinatura_base64', '')

        try: data_f = datetime.strptime(data, '%Y-%m-%d').strftime('%d/%m/%Y')
        except Exception: data_f = data

        conn = get_db_connection()
        cursor = conn.cursor()
        upsert_entrega_efetuada(cursor, nf, data_f, recebedor, assinatura)
        conn.commit()
        conn.close()
        return render_template('baixa_entrega_mobile_sucesso.html', nf=nf)

    hoje = datetime.today().strftime('%Y-%m-%d')
    return render_template('baixa_entrega_mobile.html', data_hoje=hoje)


@app.route('/buscar_nf_baixa', methods=['GET'])
def buscar_nf_baixa():
    nf_busca = request.args.get('nf_baixa', '').strip()
    if not nf_busca: return redirect('/relatorio_faturamento?erro=Digite uma Nota Fiscal.')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM faturamento WHERE nf = ?", (nf_busca,))
    nota = cursor.fetchone()
    cursor.execute("SELECT * FROM entregas_efetuadas WHERE nota_fiscal = ?", (nf_busca,))
    baixa_existente = cursor.fetchone()
    conn.close()

    if not nota: return redirect(f'/relatorio_faturamento?erro=Nota Fiscal {nf_busca} nao localizada.')

    nota_dict = {"nf": nota["nf"], "cliente": nota["cliente"], "transportadora": nota["transportadora"]}

    if baixa_existente:
        nota_dict['ja_entregue'] = True
        nota_dict['data_entrega'] = baixa_existente['data_entrega']
        nota_dict['recebedor'] = baixa_existente['recebedor']
        nota_dict['assinatura'] = baixa_existente['assinatura']
    else:
        nota_dict['ja_entregue'] = False

    return render_template('efetuar_baixa.html', nota=nota_dict)


@app.route('/salvar_baixa_entrega', methods=['POST'])
def salvar_baixa_entrega():
    nf = request.form.get('nota_fiscal', '').strip()
    recebedor = request.form.get('recebedor', '').strip()
    assinatura = request.form.get('assinatura', '').strip()
    data_entrega = request.form.get('data_entrega', '').strip()

    if "-" in data_entrega:
        try: data_entrega = datetime.strptime(data_entrega, '%Y-%m-%d').strftime('%d/%m/%Y')
        except Exception: pass

    if not data_entrega: data_entrega = datetime.now().strftime('%d/%m/%Y')
    if not nf: return redirect('/relatorio_faturamento?erro=Dados invalidos.')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        upsert_entrega_efetuada(cursor, nf, data_entrega, recebedor, assinatura)
        conn.commit()
        msg, tipo_msg = f"Baixa da NF {nf} realizada com sucesso!", "sucesso"
    except Exception as e:
        conn.rollback()
        msg, tipo_msg = f"Erro no banco: {str(e)}", "erro"
    finally:
        conn.close()

    return redirect(f'/relatorio_faturamento?msg_sucesso={msg}' if tipo_msg == "sucesso" else f'/relatorio_faturamento?erro={msg}')


@app.route('/obter_itens_nota/<nf>', methods=['GET'])
def obter_itens_nota(nf):
    nf_busca = str(nf).strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT valor_total_nf FROM faturamento WHERE nf = ?", (nf_busca,))
    nota_principal = cursor.fetchone()
    valor_nota = nota_principal['valor_total_nf'] if nota_principal else "R$ 0,00"
    
    cursor.execute("SELECT codigo_item, descricao_item, qtde, um, peso_unitario, peso_total FROM faturamento_itens WHERE nf = ? ORDER BY id ASC", (nf_busca,))
    rows = cursor.fetchall()
    conn.close()
    
    peso_acumulado = 0.0
    itens_normalizados = []
    
    for r in rows:
        item_ajustado = {
            'codigo_item': r['codigo_item'], 'descricao_item': r['descricao_item'], 'qtde': r['qtde'],
            'um': r['um'], 'peso_unitario': r['peso_unitario'], 'peso_total': r['peso_total']
        }
        itens_normalizados.append(item_ajustado)
        peso_raw = str(item_ajustado['peso_total']).strip()
        if ',' in peso_raw and '.' in peso_raw:
            peso_raw = peso_raw.replace('.', '').replace(',', '.')
        elif ',' in peso_raw:
            peso_raw = peso_raw.replace(',', '.')
            
        try: peso_acumulado += float(peso_raw)
        except Exception: pass

    peso_formatado = f"{peso_acumulado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " KG"
    return {"itens": itens_normalizados, "valor_total": valor_nota, "peso_total": peso_formatado}


# ============================================================
# EXPORTAÇÕES PARCIAIS DE RELATÓRIOS EM EXCEL
# ============================================================

@app.route('/exportar')
@login_requerido()
def exportar():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT cliente AS Cliente, nota_fiscal AS [Nota Fiscal], data AS Data, tratativa AS Tratativa, motivo AS Motivo FROM ocorrencias ORDER BY id DESC", conn)
    conn.close()
    df.to_excel(EXCEL_OCORRENCIAS, index=False)
    return send_file(EXCEL_OCORRENCIAS, as_attachment=True, download_name='relatorio_ocorrencias.xlsx')


@app.route('/exportar_coletas')
@login_requerido()
def exportar_coletas():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT cliente AS Cliente, nota_fiscal AS [Nota Fiscal], transportadora AS Transportadora, data_solicitacao AS [Data Solicitação], status AS Status FROM coletas ORDER BY id DESC", conn)
    conn.close()
    df.to_excel(EXCEL_COLETAS, index=False)
    return send_file(EXCEL_COLETAS, as_attachment=True, download_name='relatorio_coletas.xlsx')


@app.route('/exportar_transportadoras')
@login_requerido()
def exportar_transportadoras():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT name AS Transportadora, telephone AS Telefone, responsavel AS Responsável FROM transportadoras ORDER BY name ASC", conn)
    conn.close()
    df.to_excel(EXCEL_TRANSPORTADORAS, index=False)
    return send_file(EXCEL_TRANSPORTADORAS, as_attachment=True, download_name='cadastro_transportadoras.xlsx')


@app.route('/exportar_canhotos')
@login_requerido()
def exportar_canhotos():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT cliente AS Cliente, nota_fiscal AS [Nota Fiscal], data_recebimento AS [Data Recebimento], status AS Status, observacoes AS Observações FROM canhotos ORDER BY id DESC", conn)
    conn.close()
    df.to_excel(EXCEL_CANHOTOS, index=False)
    return send_file(EXCEL_CANHOTOS, as_attachment=True, download_name='relatorio_canhotos.xlsx')


@app.route('/exportar_base_faturamento')
@login_requerido()
def exportar_base_faturamento():
    excel_fat = buscar_ultimo_faturamento()
    if excel_fat and os.path.exists(excel_fat):
        return send_file(excel_fat, as_attachment=True, download_name=os.path.basename(excel_fat))
    return "Erro: Planilha não localizada."


@app.route('/exportar_base_expedicao')
@login_requerido()
def exportar_base_expedicao():
    excel_exp = obter_planilha_expedicao_conciliacao()
    if excel_exp and os.path.exists(excel_exp):
        return send_file(excel_exp, as_attachment=True, download_name=os.path.basename(excel_exp))
    return "Erro: Planilha não localizada."


@app.route('/exportar_faturamento_filtrado', methods=['GET'])
@login_requerido()
def exportar_faturamento_filtrado():
    filtro_inicio = request.args.get('data_inicio', '').strip()
    filtro_fim = request.args.get('data_fim', '').strip()
    filtro_nf = request.args.get('busca_nf', '').strip()
    filtro_cliente = request.args.get('busca_cliente', '').strip()
    busca_status = request.args.get('busca_status', '').strip()

    excel_fat = buscar_ultimo_faturamento()
    excel_exp = buscar_ultima_expedicao()

    if not excel_fat: return "Erro: Planilha não localizada."

    try:
        df = pd.read_excel(excel_fat)
        df['Emissão da NF-e'] = pd.to_datetime(df['Emissão da NF-e'], errors='coerce')
        df['Número da NF-e'] = df['Número da NF-e'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

        if filtro_inicio and filtro_fim:
            df = df[(df['Emissão da NF-e'] >= pd.to_datetime(filtro_inicio)) & (df['Emissão da NF-e'] <= pd.to_datetime(filtro_fim))]
        if filtro_cliente:
            df = df[df['Cliente'].str.contains(filtro_cliente, case=False, na=False)]
        if filtro_nf:
            df = df[df['Número da NF-e'].str.contains(filtro_nf, case=False, na=False)]

        conn = get_db_connection()
        df_ent = pd.read_sql_query("SELECT * FROM entregas_efetuadas", conn)
        conn.close()
        df_ent['nota_fiscal'] = df_ent['nota_fiscal'].astype(str).str.strip()
        df_ent = df_ent.drop_duplicates(subset=['nota_fiscal'])
        df = df.merge(df_ent, left_on='Número da NF-e', right_on='nota_fiscal', how='left')

        if excel_exp:
            df_exp = pd.read_excel(excel_exp)
            col_doc = df_exp.columns[0]
            col_transp = df_exp.columns[3]
            df_exp[col_doc] = df_exp[col_doc].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            df_exp = df_exp.drop_duplicates(subset=[col_doc])
            df = df.merge(df_exp[[col_doc, col_transp]], left_on='Número da NF-e', right_on=col_doc, how='left')

        df['STATUS EXPEDIÇÃO'] = df.apply(
            lambda r: 'ENTREGUE' if pd.notna(r['data_entrega']) and r['data_entrega'] != ""
            else 'EXPEDIDO' if pd.notna(r.get(df_exp.columns[3] if excel_exp else 'Transportadora')) and r[df_exp.columns[3] if excel_exp else 'Transportadora'] != ""
            else 'NÃO EXPEDIDO', axis=1
        )

        mapa_wms = mapear_posicoes_wms_de_excel(obter_planilha_wms_conciliacao())
        itens_por_nf_export = {}
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT nf, codigo_item FROM faturamento_itens WHERE codigo_item IS NOT NULL AND codigo_item <> ''")
            for row_item in cur.fetchall():
                nf_item = _limpar_numero_nf(row_item['nf'])
                codigo_item = _limpar_codigo_material(row_item['codigo_item'])
                if nf_item and codigo_item:
                    itens_por_nf_export.setdefault(nf_item, set()).add(codigo_item)
            conn.close()
            itens_por_nf_export = {nf: sorted(codigos) for nf, codigos in itens_por_nf_export.items()}
        except Exception:
            itens_por_nf_export = {}

        def resolver_dw_wms_export(row):
            status = row.get('STATUS EXPEDIÇÃO')
            if status == 'ENTREGUE':
                return 'ENTREGUE'
            if status == 'EXPEDIDO':
                return 'EXPEDIDA'
            nf_row = _limpar_numero_nf(row.get('Número da NF-e'))
            return _posicao_wms_para_nf(nf_row, mapa_wms, itens_por_nf_export)

        df['DW POSICAO WMS'] = df.apply(resolver_dw_wms_export, axis=1)

        if busca_status: df = df[df['STATUS EXPEDIÇÃO'] == busca_status]

        df = df.fillna("")
        arquivo = os.path.join(BASE_DIR, 'faturamento_conciliado_filtrado.xlsx')
        df.to_excel(arquivo, index=False)
        return send_file(arquivo, as_attachment=True, download_name='relatorio_faturamento_conciliado.xlsx')
    except Exception as e:
        return f"Erro ao exportar: {str(e)}"


# ============================================================
# 🎯 MÓDULO EMISSOR DE ETIQUETAS E API DE INTEGRAÇÃO SEQUENCIAL
# ============================================================

@app.route('/gerador_etiquetas')
def gerador_etiquetas():
    return render_template('gerador_etiquetas.html')


@app.route('/api/itens_nota/<nf>')
def api_itens_nota(nf):
    nf_busca = str(nf).strip()
    
    conn = get_db_connection()
    border_cursor = conn.cursor()
    border_cursor.execute("SELECT cliente, transportadora, pedido FROM faturamento WHERE nf = ?", (nf_busca,))
    cabecalho = border_cursor.fetchone()
    conn.close()
    
    if not cabecalho:
        return jsonify({"status": "erro", "mensagem": f"Nota Fiscal {nf_busca} não encontrada no faturamento."}), 404

    excel_fat = buscar_ultimo_faturamento()
    if not excel_fat:
        return jsonify({"status": "erro", "mensagem": "Arquivo Excel de faturamento não localizado."}), 404
        
    try:
        # 🟢 ENGENHARIA DE-PARA EAN INTEGRADA:
        # Carrega a tabela viva de EANs salvos na mesma pasta do sistema
        dict_ean_mapeado = {}
        caminho_ean = os.path.join(BASE_DIR, 'CODIGOS EAN.xlsx')
        if os.path.exists(caminho_ean):
            try:
                df_ean_planilha = pd.read_excel(caminho_ean)
                for _, r in df_ean_planilha.iterrows():
                    cod_item_v = str(r.get('CÓDIGO', '')).strip()
                    ean_v = str(r.get('Cód EAN', '')).strip().split('.')[0]
                    if cod_item_v and ean_v and ean_v != 'nan':
                        dict_ean_mapeado[cod_item_v] = ean_v
            except Exception as e_ean:
                print(f"⚠️ Erro ao processar tabela de-para EAN: {e_ean}")

        df_excel = pd.read_excel(excel_fat)
        if df_excel.empty:
            return jsonify({"status": "erro", "mensagem": "O arquivo de faturamento está vazio."}), 404

        # 🎯 PRESERVADO INTEGRAMENTE: Seus mapeamentos exatos de colunas locais
        col_nf = df_excel.columns[1]
        col_codigo_item = df_excel.columns[13] # 📜 Captura a coluna de Código do Item (Índice 13)
        col_prod_desc = df_excel.columns[14]
        col_um = df_excel.columns[16]
        col_qtde = df_excel.columns[15]

        df_excel[col_nf] = df_excel[col_nf].ffill()
        df_excel[col_nf] = df_excel[col_nf].astype(str).str.split('.').str[0].str.strip()

        df_nota = df_excel[df_excel[col_nf] == nf_busca]

        if df_nota.empty:
            return jsonify({"status": "erro", "mensagem": f"A nota {nf_busca} não possui itens no Excel."}), 404

        lista_itens = []
        idx = 1

        for _, row in df_nota.iterrows():
            val_um = str(row[col_um]).strip().upper() if pd.notna(row[col_um]) else ""
            desc_prod = str(row[col_prod_desc]).strip() if pd.notna(row[col_prod_desc]) else ""
            cod_item_real = str(row[col_codigo_item]).strip() if pd.notna(row[col_codigo_item]) else ""

            is_item_real = (val_um != "" and val_um not in ('NAN', 'NONE', '-NO VALUE-', '0', '0.0'))

            if is_item_real and desc_prod:
                try:
                    qtd_limpa = int(float(row[col_qtde])) if pd.notna(row[col_qtde]) else 1
                except:
                    qtd_limpa = 1

                # ⚡ REALIZA O CRUSAMENTO DO DE-PARA:
                # Se encontrar o código na planilha EAN, injeta o número EAN. 
                # Se não encontrar, repassa o próprio código original como contingência de segurança.
                ean_final = dict_ean_mapeado.get(cod_item_real, cod_item_real)

                lista_itens.append({
                    "id": idx,
                    "codigo_item": cod_item_real,
                    "codigo_ean": ean_final, # 🔢 Enviado com sucesso para o HTML chavear
                    "descricao": desc_prod.upper(),
                    "qtd_total": qtd_limpa
                })
                idx += 1

        if not lista_itens:
            return jsonify({"status": "erro", "mensagem": f"Nenhum produto físico localizado para a nota {nf_busca}."}), 404

        nota_encontrada = {
            "cliente": cabecalho["cliente"],
            "transportadora": cabecalho["transportadora"],
            "pedido": cabecalho["pedido"] if cabecalho["pedido"] else "-",
            "pedido_compra": cabecalho["pedido"] if cabecalho["pedido"] else "-", 
            "itens": lista_itens
        }
        
        return jsonify(nota_encontrada)

    except Exception as e:
        print(f"❌ Erro ao ler Excel na API de Etiquetas: {str(e)}")
        return jsonify({"status": "erro", "mensagem": f"Erro ao processar o Excel: {str(e)}"}), 500

# ============================================================
# PORTAS DE ENTRADA (ROTAS) DO CANHOTO DIGITAL MOBILE
# ============================================================

@app.route('/api/salvar_canhoto', methods=['POST'])
def salvar_canhoto():
    dados = request.get_json()
    if not dados:
        return jsonify({"status": "erro", "mensagem": "Nenhum dado recebido"}), 400
        
    motorista = dados.get('motorista')
    rg = dados.get('rg')
    nota_fiscal = dados.get('nota_fiscal', '').strip() # 🟢 Captura a NF vinda do Celular
    transportadora = dados.get('transportadora')
    assinatura = dados.get('assinatura')
    
    if not all([motorista, transportadora, signature_val := assinatura]):
        return jsonify({"status": "erro", "mensagem": "Motorista, Transportadora e Assinatura sao obrigatorios!"}), 400
        
    agora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 🔥 Grava salvando a Nota Fiscal na sua respectiva coluna distinta
        cursor.execute("""
            INSERT INTO canhotos_digitais (motorista, rg, nota_fiscal, transportadora, assinatura_base64, data_hora)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (motorista.upper().strip(), rg.strip(), nota_fiscal, transportadora.upper().strip(), assinatura, agora))
        conn.commit()
        
        # ⚡ CONCILIAÇÃO AUTOMÁTICA ATIVADA: Abastece o relatório de faturamento na mesma hora!
        conciliar_faturamento_automatico(nota_fiscal, motorista, "ASSINATURA DIGITAL TELA")
        
        return jsonify({"status": "sucesso", "mensagem": "Canhoto assinado e salvo com sucesso!"})
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    finally:
        conn.close()


@app.route('/api/importar_canhoto_whatsapp', methods=['POST'])
@login_requerido()
def importar_canhoto_whatsapp():
    try:
        motorista = request.form.get('motorista', '').strip()
        rg = request.form.get('rg', '').strip()
        nota_fiscal = request.form.get('nota_fiscal', '').strip()
        transportadora = request.form.get('transportadora', '').strip()
        arquivo = request.files.get('file')

        if not all([motorista, transportadora, arquivo]):
            return jsonify({"status": "erro", "mensagem": "Motorista, Transportadora e Arquivo são obrigatórios!"}), 400

        imagem_bytes = arquivo.read()
        extensao = arquivo.filename.split('.')[-1].lower()
        if extensao not in ['jpg', 'jpeg', 'png']:
            return jsonify({"status": "erro", "mensagem": "Formato de imagem inválido. Use JPG ou PNG."}), 400

        imagem_base64 = f"data:image/{extensao};base64," + base64.b64encode(imagem_bytes).decode('utf-8')
        agora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO canhotos_digitais (motorista, rg, nota_fiscal, transportadora, assinatura_base64, data_hora)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (motorista.upper(), rg.strip(), nota_fiscal.strip(), transportadora.upper(), imagem_base64, agora))
        conn.commit()
        conn.close()

        # ⚡ CONCILIAÇÃO AUTOMÁTICA ATIVADA: Abastece o relatório de faturamento na mesma hora!
        conciliar_faturamento_automatico(nota_fiscal, motorista, "FOTO CANHOTO FÍSICO")

        return jsonify({"status": "sucesso", "mensagem": "Foto do WhatsApp integrada com sucesso!"})

    except Exception as e:
        print(f"❌ Erro ao importar foto do WhatsApp: {str(e)}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

        # ============================================================
# 🔥 ADICIONE ESTE NOVO BLOCO LOGO ABAIXO (SEM APAGAR O DE CIMA)
# ============================================================
@app.route('/api/salvar_canhoto_zip', methods=['POST'])
@login_requerido()
def api_salvar_canhoto_zip():
    """Registra a baixa no banco e salva a foto tratando reentregas para evitar sobreposição física"""
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({"status": "erro", "mensagem": "Dados não recebidos"}), 400

        nf = dados.get('nota_fiscal', '').strip()
        motorista = dados.get('motorista', '').strip()
        data_recebimento = dados.get('data_recebimento', '').strip()
        observacoes = dados.get('observacoes', '').strip()
        nome_arquivo = dados.get('nome_arquivo', '').strip()
        imagem_base64 = dados.get('imagem_base64', '')
        is_reentrega = dados.get('reentrega', False) # 🚨 Capta a flag vinda do clique do Adriano

        if not nf:
            return jsonify({"status": "erro", "mensagem": "Número de Nota Fiscal inválido"}), 400

        nf_limpa = nf.lstrip('0').strip()

        if "-" in data_recebimento:
            try:
                dt_obj = datetime.strptime(data_recebimento, '%Y-%m-%d')
                data_recebimento = dt_obj.strftime('%d/%m/%Y')
            except:
                pass
        if not data_recebimento:
            data_recebimento = datetime.now().strftime('%d/%m/%Y')

        hora_atual = datetime.now().strftime('%H:%M:%S')
        data_hora_painel = f"{data_recebimento} {hora_atual}"
        usuario_logado = session.get('usuario_nome', 'ESTEIRA WHATSAPP')
        
        # Ajusta os textos de auditoria baseado no tipo da entrega
        status_logistico = "ENTREGUE" if not is_reentrega else "REENTREGA EFETUADA"
        recebedor_formatado = f"MOT: {str(motorista).upper().strip()}"
        texto_auditoria = f"BAIXA ZIP | OPERADOR: {str(usuario_logado).upper().strip()}"
        if is_reentrega:
            texto_auditoria += " | **REENTREGA APÓS OCORRÊNCIA**"

        # 📁 1️⃣ SALVAMENTO DO ARQUIVO FÍSICO COM TRATAMENTO DE REENTREGA
        if imagem_base64 and "," in imagem_base64:
            try:
                string_foto = imagem_base64.split(",")[1]
                dados_foto = base64.b64decode(string_foto)
                
                data_nome_arquivo = data_recebimento.replace("/", "-")
                hora_nome_arquivo = hora_atual.replace(":", "")
                
                # 🎯 Se for reentrega, bota o carimbo no nome para o Windows não apagar o canhoto antigo!
                sufixo = "_REENTREGA" if is_reentrega else ""
                nome_foto_final = f"{nf_limpa}_{data_nome_arquivo}_{hora_nome_arquivo}{sufixo}.jpg"
                caminho_foto_final = os.path.join(PASTA_CANHOTOS_OK, nome_foto_final)
                
                with open(caminho_foto_final, "wb") as f:
                    f.write(dados_foto)
            except Exception as e:
                print(f"⚠️ Alerta ao salvar arquivo físico: {str(e)}")

        # ⚡ 2️⃣ INSERÇÃO ATÔMICA NO BANCO SQLITE
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Alimenta os dados de entrega reais na tabela 'entregas_efetuadas'
        upsert_entrega_efetuada(
            cursor,
            nf_limpa,
            data_recebimento,
            recebedor_formatado,
            texto_auditoria,
        )

        cursor.execute("""
            UPDATE faturamento 
            SET transportadora = ? 
            WHERE TRIM(nf) = ? OR TRIM(nf) = ?
        """, (recebedor_formatado, nf_limpa, nf))

        # Alimenta o histórico geral mudando o status para acompanhar a auditoria
        cursor.execute("""
            INSERT INTO canhotos (cliente, nota_fiscal, data_recebimento, status, observacoes)
            VALUES (?, ?, ?, ?, ?)
        """, (f"LOTE ZIP", nf_limpa, data_recebimento, status_logistico, f"Mot: {motorista} | Obs: {observacoes}"))
        
        cursor.execute("""
            INSERT INTO canhotos_digitais (motorista, rg, nota_fiscal, transportadora, assinatura_base64, data_hora)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (motorista.upper(), "CONFERIDO (ZIP)", nf_limpa, "WHATSAPP ESTEIRA", imagem_base64, data_hora_painel))
        
        conn.commit()
        conn.close()

        print(f"🎯 [ESTEIRA REENTREGA] NF {nf_limpa} processada com sucesso!")
        return jsonify({"status": "sucesso", "mensagem": f"✔️ NF {nf_limpa} arquivada!"}), 200

    except Exception as e:
        print(f"❌ [ERRO ROTA ZIP]: {str(e)}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
@app.route('/api/notas_ja_baixadas', methods=['GET'])
def api_notas_ja_baixadas():
    """Devolve a lista de todas as Notas Fiscais que já estão entregues no banco"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Busca todas as NFs que já possuem registro de entrega efetuada
        cursor.execute("SELECT DISTINCT TRIM(nota_fiscal) FROM entregas_efetuadas")
        notas = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
        return jsonify({"status": "sucesso", "notas": notas}), 200
    except Exception as e:
        return jsonify({"status": "erro", "notas": []}), 500
    
    # ============================================================
# 📱 API DE INTEGRAÇÃO: ENTREGAR DADOS EXTRAÍDOS DO WHATSAPP
# ============================================================
@app.route('/api/dados_canhotos_whatsapp', methods=['GET'])
def api_dados_canhotos_whatsapp():
    """ API JSON que despeja a correlação do WhatsApp para a tela da TV """
    dados_whatsapp = ler_canhotos_whatsapp_vivos()
    return jsonify(dados_whatsapp)

@app.route('/tv_canhotos_whatsapp', methods=['GET'])
def tv_canhotos_whatsapp():
    """ Rota que renderiza a interface visual de triagem do WhatsApp """
    return render_template('canhotos_assinados.html')


# 🔥 NOVA ROTA EXCLUSIVA DE EDIÇÃO SOLICITADA PELO ADRIANO
@app.route('/api/editar_canhoto', methods=['POST'])
@login_requerido()
def editar_canhoto():
    try:
        dados = request.get_json()
        canhoto_id = dados.get('id')
        motorista = dados.get('motorista', '').strip()
        rg = dados.get('rg', '').strip()
        nota_fiscal = dados.get('nota_fiscal', '').strip()
        transportadora = dados.get('transportadora', '').strip()

        if not canhoto_id or not motorista or not transportadora:
            return jsonify({"status": "erro", "mensagem": "ID, Motorista e Transportadora são obrigatórios!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE canhotos_digitais 
            SET motorista = ?, rg = ?, nota_fiscal = ?, transportadora = ?
            WHERE id = ?
        """, (motorista.upper(), rg, nota_fiscal, transportadora.upper(), canhoto_id))
        conn.commit()
        conn.close()

        # ⚡ CONCILIAÇÃO AUTOMÁTICA ATIVADA: Se alterar a nota na edição, atualiza a baixa também!
        conciliar_faturamento_automatico(nota_fiscal, motorista, "REGISTRO ALTERADO OPERACIONALMENTE")

        return jsonify({"status": "sucesso", "mensagem": "Registro updated com sucesso!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    

# 🔥 NOVA ROTA EXCLUSIVA DE EXCLUSÃO SOLICITADA PELO ADRIANO
# 🔥 ROTA DE EXCLUSÃO CORRIGIDA COM ENGENHARIA REVERSA DE STATUS OPERACIONAL
@app.route('/api/excluir_canhoto', methods=['POST'])
@login_requerido()
def excluir_canhoto():
    try:
        dados = request.get_json()
        canhoto_id = dados.get('id')

        if not canhoto_id:
            return jsonify({"status": "erro", "mensagem": "ID do registro não informado!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. PASSO DA ENGENHARIA REVERSA: Localiza as Notas Fiscais antes de apagar o canhoto
        cursor.execute("SELECT nota_fiscal FROM canhotos_digitais WHERE id = ?", (canhoto_id,))
        registro = cursor.fetchone()
        
        if registro and registro[0]:
            nota_fiscal_str = registro[0]
            # Quebra o lote de notas caso o registro tenha mais de uma por vírgula
            notas_individuais = [n.strip() for n in str(nota_fiscal_str).split(',') if n.strip()]
            
            for nf in notas_individuais:
                nf_limpa = nf.lstrip('0').strip()
                if not nf_limpa:
                    continue
                
                # 2. Caminho Inverso: Apaga o vínculo de entrega efetuada (tira o selo VERDE)
                cursor.execute("DELETE FROM entregas_efetuadas WHERE nota_fiscal = ? OR nota_fiscal = ?", (nf_limpa, nf))

        cursor.execute("DELETE FROM canhotos_digitais WHERE id = ?", (canhoto_id,))
        
        conn.commit()
        conn.close()

        print(f"✔️ [REVERSÃO DE STATUS] Registro {canhoto_id} excluído. Notas fiscais redefinidas para o status anterior.")
        return jsonify({"status": "sucesso", "mensagem": "Registro excluído e faturamento restaurado!"})
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
    # 🔥 ROTA DE ESTORNO UNIVERSAL - SOLICITADA PELO ADRIANO
# Limpa qualquer teste ou erro de digitação direto do Relatório de Faturamento
@app.route('/api/estornar_baixa_manual', methods=['POST'])
@login_requerido()
def estornar_baixa_manual():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({"status": "erro", "mensagem": "Dados não recebido!"}), 400

        nf_bruta = dados.get('nota_fiscal', '').strip()
        if not nf_bruta:
            return jsonify({"status": "erro", "mensagem": "Número da Nota Fiscal não informado!"}), 400

        # Normaliza tirando espaços e zeros à esquerda para dar o match perfeito
        nf_limpa = nf_bruta.lstrip('0').strip()

        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Deleta a linha de baixa oficial da tabela mestre de entregas
        cursor.execute("DELETE FROM entregas_efetuadas WHERE nota_fiscal = ? OR nota_fiscal = ?", (nf_limpa, nf_bruta))

        # 2. Remove canhotos mobile com match exato (NF isolada ou em lote separado por vírgula)
        cursor.execute("""
            DELETE FROM canhotos_digitais
            WHERE nota_fiscal = ? OR nota_fiscal = ?
               OR nota_fiscal LIKE ? OR nota_fiscal LIKE ?
               OR nota_fiscal LIKE ? OR nota_fiscal LIKE ?
        """, (
            nf_limpa, nf_bruta,
            f"{nf_limpa},%", f"%,{nf_limpa},%", f"%,{nf_limpa}",
            f"{nf_bruta},%", f"%,{nf_bruta}",
        ))

        conn.commit()
        conn.close()

        print(f"✔️ [ESTORNO REALIZADO] Nota Fiscal {nf_bruta} restaurada ao status original com sucesso.")
        return jsonify({"status": "sucesso", "mensagem": f"Baixa da NF {nf_bruta} estornada com sucesso!"})

    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route('/api/listar_canhotos', methods=['GET'])
@login_requerido()
def listar_canhotos():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, motorista, rg, nota_fiscal, transportadora, data_hora, assinatura_base64 FROM canhotos_digitais ORDER BY id DESC")
    linhas = cursor.fetchall()
    conn.close()
    
    resultado = []
    for linha in linhas:
        resultado.append({
            "id": linha["id"],
            "motorista": linha["motorista"],
            "rg": linha["rg"],
            "nota_fiscal": linha["nota_fiscal"],
            "transportadora": linha["transportadora"],  
            "data_hora": linha["data_hora"],
            "assinatura": linha["assinatura_base64"]
        })
    return jsonify(resultado)


@app.route('/canhoto')
def tela_canhoto():
    return render_template('canhoto.html')


@app.route('/canhotos_assinados')
def tela_canhotos_assinados():
    lista_transp = ler_transportadoras_db()
    return render_template('canhotos_assinados.html', transportadoras=lista_transp)


# ============================================================
# EXECUÇÃO DO SERVIDOR E INTERFACE NATIVA DESKTOP
# ============================================================

def rodar_flask(porta=5000):
    try:
        app.run(host='0.0.0.0', port=porta, debug=False, use_reloader=False)
    except Exception as e:
        log_path = os.path.join(BASE_DIR, 'erro_executavel.txt')
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"Erro ao iniciar o Flask:\n{str(e)}\n\n")

@app.route('/painel_indicadores')
def painel_indicadores():
    """Renderiza a tela de Dashboard rotativo da expedição."""
    return render_template('painel_indicadores.html')

@app.route('/tv_coletas_fob', methods=['GET']) # 👈 ADICIONADO: Link direto com o configurador
def tv_coletas_fob():
    if 'usuario_id' not in session:
        return redirect('/login')
    # ... aqui ele faz a mesma busca de coletas pendentes ...
    return render_template('relatorio_coletas.html') # Renderiza a tela de coletas direto no frame da TV

@app.route('/monitor', methods=['GET'])
@app.route('/monitor_tv', methods=['GET']) # 👈 ADICIONADO: Agora aceita o chamado da TV
def monitor():
    if 'usuario_id' not in session:
        return redirect('/login')
    # ... resto do seu código padrão da rota monitor ...
    return render_template('monitor.html') # ou o nome do seu template principal

@app.route('/api/dados_dashboard_expedicao')
def api_dados_dashboard_expedicao():
    """Processa a base real de faturamento eliminando duplicidades de itens por NF para não extrapolar valores."""
    import sqlite3
    from datetime import datetime
    from flask import jsonify, request

    try:
        # 🎯 CAPTURA DOS PARÂMETROS
        dia_filtro = request.args.get('data', '').strip()  # Formato: YYYY-MM-DD
        mes_filtro = request.args.get('mes', '').strip()   # Formato: MM/YYYY

        # Contextualiza o mês correto com base no filtro aplicado
        if dia_filtro:
            try:
                dt_f = datetime.strptime(dia_filtro, '%Y-%m-%d')
                mes_contexto = dt_f.strftime('%m/%Y')
            except:
                mes_contexto = datetime.now().strftime('%m/%Y')
        else:
            mes_contexto = mes_filtro if mes_filtro else datetime.now().strftime('%m/%Y')

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Garante a existência da tabela do De-Para
        if database_adapter.is_sqlite():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS de_para_modais (
                    transportadora TEXT PRIMARY KEY,
                    modal_correto TEXT
                )
            """)
        
        # 🔍 CORREÇÃO CRÍTICA (MAX/GROUP BY): Agrupa por NF para impedir que o LEFT JOIN multiplique os valores das notas
        cursor.execute("""
            SELECT f.nf, f.emissao, f.cliente, f.municipio, f.uf, f.cep, f.transportadora, 
                   MAX(f.valor_total_nf) as valor_total_nf, m.modal_correto
            FROM faturamento f
            LEFT JOIN de_para_modais m ON TRIM(UPPER(f.transportadora)) = TRIM(UPPER(m.transportadora))
            GROUP BY f.nf, f.emissao, f.cliente, f.municipio, f.uf, f.cep, f.transportadora, m.modal_correto
        """)
        rows = cursor.fetchall()
        conn.close()
        
        # Inicialização dos dicionários de controle
        modais_qtd = {"NOSSO CARRO": 0, "FOB": 0, "CLIENTE RETIRA": 0, "CIF": 0, "OUTROS": 0}
        modais_valor = {"NOSSO CARRO": 0.0, "FOB": 0.0, "CLIENTE RETIRA": 0.0, "CIF": 0.0, "OUTROS": 0.0}
        diario_map = {}
        notas_detalhadas = []
        
        def extrair_formatos_data(dt_input):
            if not dt_input: return None, None, None
            dt_str = str(dt_input).strip().split()[0]
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    dt = datetime.strptime(dt_str, fmt)
                    return dt.strftime('%m/%Y'), dt.strftime('%d/%m'), dt.strftime('%Y-%m-%d')
                except: pass
            return None, None, None

        def limpar_float(val):
            if not val: return 0.0
            try:
                val_limpo = str(val).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.').strip()
                if val_limpo.count('.') > 1:
                    partes = val_limpo.split('.')
                    val_limpo = "".join(partes[:-1]) + "." + partes[-1]
                return float(val_limpo)
            except:
                return 0.0

        META_DIARIA_PADRAO = 467333.26

        for r in rows:
            mes_ano_nf, dia_mes_nf, data_iso_nf = extrair_formatos_data(r['emissao'])
            
            # Valida escopo do mês corrente/contexto
            if mes_ano_nf != mes_contexto:
                continue

            valor = limpar_float(r['valor_total_nf'])
            
            # Acumula a linha temporal do mês cheio (Grafico de Linha da Torre)
            if dia_mes_nf:
                diario_map[dia_mes_nf] = diario_map.get(dia_mes_nf, 0.0) + valor

            # ⚡ ISOLAMENTO DO FILTRO DIÁRIO: Restringe as barras e a auditoria ao dia selecionado
            if dia_filtro and data_iso_nf != dia_filtro:
                continue

            # Classificação inteligente de modais
            modal_bruto = str(r['modal_correto']).upper().strip() if r['modal_correto'] else ""
            transportadora_bruta = str(r['transportadora']).upper().strip() if r['transportadora'] else ""
            
            if "NOSSO" in modal_bruto or "PROPRIA" in modal_bruto or "PRÓPRIA" in modal_bruto:
                modal_final = "NOSSO CARRO"
            elif "FOB" in modal_bruto:
                modal_final = "FOB"
            elif "RETIRA" in modal_bruto:
                modal_final = "CLIENTE RETIRA"
            elif "CIF" in modal_bruto:
                modal_final = "CIF"
            else:
                if "NOSSO" in transportadora_bruta or "PROPRIO" in transportadora_bruta or "PRÓPRIO" in transportadora_bruta or "FROTA" in transportadora_bruta:
                    modal_final = "NOSSO CARRO"
                elif "RETIRA" in transportadora_bruta or "CLIENTE" in transportadora_bruta:
                    modal_final = "CLIENTE RETIRA"
                elif "FOB" in transportadora_bruta:
                    modal_final = "FOB"
                elif "CIF" in transportadora_bruta:
                    modal_final = "CIF"
                else:
                    modal_final = "OUTROS"
                
            modais_qtd[modal_final] += 1
            modais_valor[modal_final] += valor

            chaves_row = r.keys() if hasattr(r, 'keys') else []
            nf_val = r['nf'] if 'nf' in chaves_row else (r['NF'] if 'NF' in chaves_row else "N/A")

            notas_detalhadas.append({
                "nf": nf_val,
                "data": data_iso_nf if data_iso_nf else (dia_mes_nf if dia_mes_nf else "N/A"),
                "cliente": str(r['cliente']).strip() if r['cliente'] else "Não Informado",
                "municipio": str(r['municipio']).strip() if r['municipio'] else "",
                "uf": str(r['uf']).strip() if r['uf'] else "",
                "transportadora": transportadora_bruta if transportadora_bruta else "FROTA PRÓPRIA",
                "valor": valor
            })
                
        # Estrutura a linha de tendência do mês
        faturamento_diario = []
        for d in sorted(diario_map.keys(), key=lambda x: (x.split('/')[1], x.split('/')[0])):
            v_realizado = diario_map[d]
            porcentagem = (v_realizado / META_DIARIA_PADRAO) * 100 if META_DIARIA_PADRAO > 0 else 0
            falta_meta = max(0.0, META_DIARIA_PADRAO - v_realizado)

            faturamento_diario.append({
                "data": d, 
                "valor": round(v_realizado, 2),
                "meta": META_DIARIA_PADRAO,
                "porcentagem": round(porcentagem, 1),
                "falta": round(falta_meta, 2)
            })
            
        notas_detalhadas = sorted(notas_detalhadas, key=lambda x: x['transportadora'])

        return jsonify({
            "modalidades_qtd": modais_qtd,
            "modalidades_valor": {k: round(v, 2) for k, v in modais_valor.items()},
            "faturamento_diario": faturamento_diario,
            "notas_detalhadas": notas_detalhadas
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

# ============================================================
# 🗺️ ROTA UNIFICADA DA TORRE: PRAÇAS DE ATENDIMENTO (ULTRA SAFE)
# ============================================================
#@app.route('/tv_pracas', methods=['GET'])
@app.route('/painel_pracas', methods=['GET'])
def rota_pracas_atendimento_tv_mestre():
    """ 
    Esta rota resolve o problema definitivamente: ela aceita tanto 
    /tv_pracas (chamado pela TV) quanto /painel_pracas.
    """
    return render_template('painel_pracas.html')


@app.route('/api/telas_ativas_monitor')
def api_telas_ativas_monitor():
    """API que o painel consulta para saber quais telas o Adriano flegou."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT nome_template, descricao FROM templates_monitor WHERE ativo = 1")
        linhas = cursor.fetchall()
        conn.close()
        
        telas = [{"nome": l[0], "descricao": l[1]} for l in linhas]
        return jsonify({"telas": telas})
    except Exception as e:
        return jsonify({"error": str(e), "telas": []})
    
@app.route('/api/abrir_gerenciador_monitor', methods=['POST'])
@login_requerido()
def api_abrir_gerenciador_monitor():
    """Chama o script Tkinter em segundo plano para o Adriano flegar as telas."""
    try:
        import subprocess
        caminho_gerenciador = os.path.join(BASE_DIR, 'gerenciador_monitor.py')
        
        # Dispara o gerenciador de forma independente para não travar o Flask
        subprocess.Popen([sys.executable, caminho_gerenciador], 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE)
        return jsonify({"status": "sucesso", "mensagem": "Gerenciador aberto!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
@app.route('/espiao_torre')
def espiao_torre():
    """Painel de Auditoria Mestre: Visual ultra-compacto para caber na largura da tela."""
    import sqlite3
    from flask import request
    from datetime import datetime

    data_hoje_iso = datetime.now().strftime('%Y-%m-%d')
    data_selecionada_iso = request.args.get('data_filtro', data_hoje_iso)

    try:
        dt_obj = datetime.strptime(data_selecionada_iso, '%Y-%m-%d')
        data_formato_br = dt_obj.strftime('%d/%m/%Y')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 🎯 DEFININDO AS COLUNAS ALVO
        colunas_exibir = [
            "NF", "EMISSAO", "CLIENTE", "MUNICIPIO", "UF", 
            "CEP", "TRANSPORTADORA", "VOLUMES", "ESPECIE", 
            "PESO_BRUTO_NF", "PEDIDO", "VALOR_TOTAL_NF"
        ]
        
        colunas_sql = ", ".join(colunas_exibir)
        col_data = "EMISSAO"
        col_valor = "VALOR_TOTAL_NF"

        # 🔍 Busca as colunas no banco ordenando por Transportadora (A-Z)
        query_linhas = f"""
            SELECT {colunas_sql} FROM faturamento 
            WHERE {col_data} LIKE ? OR {col_data} LIKE ? OR {col_data} LIKE ?
            ORDER BY TRANSPORTADORA ASC
        """
        cursor.execute(query_linhas, (f"%{data_formato_br}%", f"%{data_selecionada_iso}%", f"%{data_selecionada_iso.replace('-', '/')}%"))
        linhas_banco = cursor.fetchall()
        conn.close()
        
        idx_data = colunas_exibir.index(col_data)
        idx_valor = colunas_exibir.index(col_valor)

        soma_total = 0.0
        qtd_total = len(linhas_banco)
        linhas_html = ""

        if not linhas_banco:
            linhas_html = f"<tr><td colspan='{len(colunas_exibir)}' style='text-align:center; color:#ef4444; padding: 30px;'>⚠️ Nenhuma nota localizada para este dia.</td></tr>"
        else:
            for linha in linhas_banco:
                v_float = 0.0
                valor_celula = linha[idx_valor]
                if valor_celula is not None:
                    try:
                        texto = str(valor_celula).replace("R$", "").replace(" ", "").strip()
                        if texto:
                            if "," in texto and "." in texto:
                                texto = texto.replace(".", "").replace(",", ".")
                            elif "," in texto:
                                texto = texto.replace(",", ".")
                            v_float = float(texto)
                            soma_total += v_float
                    except:
                        pass

                linhas_html += "<tr>"
                for i, valor in enumerate(linha):
                    valor_str = str(valor).strip() if valor is not None else ''
                    
                    if i == idx_data and valor_str:
                        valor_exibir = valor_str.split(" ")[0] if " " in valor_str else valor_str[:10]
                    else:
                        valor_exibir = valor_str
                        
                    if i == idx_valor:
                        valor_celula_formatado = f"R$ {v_float:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
                        linhas_html += f"<td class='text-right' style='color: #38bdf8; font-weight: bold;'>{valor_celula_formatado}</td>"
                    else:
                        linhas_html += f"<td>{valor_exibir}</td>"
                linhas_html += "</tr>"

        soma_formatada = f"R$ {soma_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
        cabecalhos_html = "".join([f"<th>{col}</th>" for col in colunas_exibir])

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>🕵️ Auditoria - Tela Cheia Compacta</title>
            <style>
                body {{ background-color: #0f172a; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; padding: 15px; margin: 0; }}
                .container-fluid {{ width: 100%; max-width: 100%; box-sizing: border-box; }}
                h1 {{ color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 8px; margin-top: 0; margin-bottom: 15px; font-size: 22px; }}
                
                .barra-filtros {{ background: #1e293b; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; display: flex; align-items: center; gap: 15px; border: 1px solid #334155; }}
                .barra-filtros label {{ font-weight: bold; color: #38bdf8; font-size: 13px; }}
                .barra-filtros input[type="date"] {{ background: #0f172a; border: 1px solid #475569; color: #fff; padding: 6px 10px; border-radius: 6px; font-size: 13px; outline: none; }}
                .barra-filtros button {{ background: #2563eb; color: white; border: none; padding: 6px 14px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 13px; }}
                
                .resumo {{ background: #1e293b; padding: 12px; border-radius: 8px; margin-bottom: 15px; border-left: 5px solid #10b981; font-size: 14px; }}
                
                /* 📐 AJUSTE DA TABELA PARA CABER NA LARGURA SEM ROLAGEM */
                .tabela-wrapper {{ width: 100%; background: #1e293b; border-radius: 8px; border: 1px solid #334155; overflow: hidden; }}
                table {{ width: 100%; border-collapse: collapse; table-layout: auto; }}
                
                /* Redução estratégica do texto e padding para espremer as colunas */
                th, td {{ padding: 6px 6px; text-align: left; border-bottom: 1px solid #334155; font-size: 10.5px; word-break: break-word; }}
                th {{ background-color: #1e293b; color: #38bdf8; font-size: 11px; font-weight: bold; border-bottom: 2px solid #475569; }}
                
                tr:hover {{ background-color: #243249; }}
                .text-right {{ text-align: right; }}
            </style>
        </head>
        <body>
            <div class="container-fluid">
                <h1>🕵️ AUDITORIA COMPACTA - VISÃO TOTAL LARGURA</h1>
                
                <div class="barra-filtros">
                    <form method="GET" action="/espiao_torre" style="display: flex; align-items: center; gap: 12px; width: 100%;">
                        <label>📅 Data do Filtro:</label>
                        <input type="date" name="data_filtro" value="{data_selecionada_iso}">
                        <button type="submit">🔍 Auto-Ajustar Tela</button>
                    </form>
                </div>
                
                <div class="resumo">
                    📊 <strong>Filtro: {data_formato_br}</strong> | Total: <strong>{qtd_total}</strong> notas lidas | Faturamento: <strong style="color:#10b981;">{soma_formatada}</strong>
                </div>

                <div class="tabela-wrapper">
                    <table>
                        <thead>
                            <tr>
                                {cabecalhos_html}
                            </tr>
                        </thead>
                        <tbody>
                            {linhas_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    except Exception as e:
        return f"<h2>❌ Erro ao processar layout compacto: {str(e)}</h2>"
    
@app.route('/auditoria_depara', methods=['GET', 'POST'])
def auditoria_depara():
    """Painel Avançado: Interface de curadoria com Filtro visível, Data Gigante e Horário de Atualização."""
    import sqlite3
    from flask import request, redirect, url_for
    from datetime import datetime

    data_hoje_iso = datetime.now().strftime('%Y-%m-%d')
    data_selecionada_iso = request.args.get('data_filtro', data_hoje_iso).strip()
    
    if not data_selecionada_iso:
        data_selecionada_iso = data_hoje_iso

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. SALVAMENTO DINÂMICO (POST)
    if request.method == 'POST':
        transportadora_alvo = request.form.get('transportadora')
        modal_apontado = request.form.get('modal_novo')
        
        if transportadora_alvo and modal_apontado:
            if database_adapter.is_sqlserver():
                transp_norm = transportadora_alvo.strip().upper()
                modal_norm = modal_apontado.strip().upper()
                cursor.execute("SELECT transportadora FROM de_para_modais WHERE transportadora = ?", (transp_norm,))
                if cursor.fetchone():
                    cursor.execute("UPDATE de_para_modais SET modal_correto = ? WHERE transportadora = ?", (modal_norm, transp_norm))
                else:
                    cursor.execute("INSERT INTO de_para_modais (transportadora, modal_correto) VALUES (?, ?)", (transp_norm, modal_norm))
            else:
                cursor.execute("""
                    INSERT INTO de_para_modais (transportadora, modal_correto)
                    VALUES (TRIM(UPPER(?)), TRIM(UPPER(?)))
                    ON CONFLICT(transportadora) DO UPDATE SET modal_correto = excluded.modal_correto
                """, (transportadora_alvo, modal_apontado))
            conn.commit()
        conn.close()
        return redirect(url_for('auditoria_depara', data_filtro=data_selecionada_iso))

    # 2. RENDERIZAÇÃO DA TELA (GET)
    try:
        # Horário exato da consulta/extração dos dados do banco
        horario_atualizacao = datetime.now().strftime('%H:%M:%S')

        try:
            dt_obj = datetime.strptime(data_selecionada_iso, '%Y-%m-%d')
            data_formato_br = dt_obj.strftime('%d/%m/%Y')
        except:
            data_formato_br = datetime.now().strftime('%d/%m/%Y')
            data_selecionada_iso = data_hoje_iso
        
        # Busca faturamento
        cursor.execute("""
            SELECT f.nf, f.emissao, f.cliente, f.transportadora, m.modal_correto, f.valor_total_nf
            FROM faturamento f
            LEFT JOIN de_para_modais m ON TRIM(UPPER(f.transportadora)) = TRIM(UPPER(m.transportadora))
            WHERE f.emissao LIKE ? OR f.emissao LIKE ? OR f.emissao LIKE ?
            ORDER BY f.transportadora ASC
        """, (f"%{data_formato_br}%", f"%{data_selecionada_iso}%", f"%{data_selecionada_iso.replace('-', '/')}%"))
        linhas_banco = cursor.fetchall()
        conn.close()

        linhas_html = ""
        opcoes_modal = ["NOSSO CARRO", "FOB", "CLIENTE RETIRA", "CIF", "OUTROS"]

        if not linhas_banco:
            linhas_html = f"<tr><td colspan='7' style='text-align:center; color:#ef4444; padding:30px; font-weight:bold;'>⚠️ Nenhuma nota fiscal localizada para o dia {data_formato_br}.</td></tr>"
        else:
            for linha in linhas_banco:
                nf, emissao, cliente, transportadora, modal_atual, valor = linha
                modal_atual = str(modal_atual).upper().strip() if modal_atual else "NÃO MAPEADO"
                
                select_options = ""
                for opt in opcoes_modal:
                    is_selected = "selected" if opt == modal_atual else ""
                    select_options += f"<option value='{opt}' {is_selected}>{opt}</option>"

                dt_limpa = str(emissao).split(" ")[0] if " " in str(emissao) else str(emissao)[:10]

                linhas_html += f"""
                <tr>
                    <td><strong>{nf}</strong></td>
                    <td>{dt_limpa}</td>
                    <td>{str(cliente)[:25]}</td>
                    <td style='color: #38bdf8; font-weight: bold;'>{transportadora}</td>
                    <td><span class="badge" style="background: { '#10b981' if modal_atual != 'NÃO MAPEADO' else '#475569' };">{modal_atual}</span></td>
                    <td>{valor}</td>
                    <td>
                        <form method='POST' action='/auditoria_depara?data_filtro={data_selecionada_iso}' style='display:flex; gap:8px; margin:0;'>
                            <input type='hidden' name='transportadora' value='{transportadora}'>
                            <select name='modal_novo' style='background:#0f172a; color:#fff; border:1px solid #475569; border-radius:4px; font-size:11px; padding:2px 5px;'>
                                {select_options}
                            </select>
                            <button type='submit' style='background:#10b981; color:white; border:none; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:bold; cursor:pointer;'>💾 Atualizar</button>
                        </form>
                    </td>
                </tr>
                """

        # HTML Base estruturado com CSS para os cards grandes de destaque
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>🕵️ Gestor de De-Para Mestre</title>
            <style>
                body {{ background-color: #0f172a; color: #f8fafc; font-family: monospace; padding: 15px; margin: 0; }}
                .container-fluid {{ width: 100%; max-width: 100%; box-sizing: border-box; }}
                h1 {{ color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 8px; margin-bottom: 15px; font-size: 20px; text-transform: uppercase; }}
                
                /* Grid de Destaques Superiores */
                .cards-topo {{ display: flex; gap: 15px; margin-bottom: 15px; }}
                .card-destaque {{ background: #1e293b; border: 1px solid #334155; padding: 12px 20px; border-radius: 8px; flex: 1; }}
                .card-destaque .label-card {{ font-size: 11px; color: #64748b; font-weight: bold; text-transform: uppercase; margin-bottom: 4px; }}
                .card-destaque .valor-card {{ font-size: 24px; font-weight: bold; color: #38bdf8; }}
                .card-destaque .valor-hora {{ font-size: 24px; font-weight: bold; color: #e2e8f0; }}

                .barra-filtros {{ background: #1e293b; padding: 12px 15px; border-radius: 8px; margin-bottom: 15px; display: flex; align-items: center; border: 1px solid #334155; }}
                .barra-filtros label {{ font-weight: bold; color: #38bdf8; font-size: 12px; margin-right: 10px; }}
                .barra-filtros input[type="date"] {{ background: #0f172a; border: 1px solid #475569; color: #38bdf8; padding: 6px 12px; border-radius: 6px; font-size: 13px; font-weight: bold; outline: none; }}
                .barra-filtros button.btn-filtrar {{ background: #2563eb; color: white; border: none; padding: 7px 18px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 12px; margin-left: 10px; }}
                
                .tabela-wrapper {{ width: 100%; background: #1e293b; border-radius: 8px; border: 1px solid #334155; overflow: hidden; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #334155; font-size: 11px; }}
                th {{ background-color: #0f172a; color: #38bdf8; font-weight: bold; border-bottom: 2px solid #475569; }}
                tr:hover {{ background-color: #243249; }}
                .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; color: white; }}
            </style>
        </head>
        <body>
            <div class="container-fluid">
                <h1>🕵️ ORQUESTRAÇÃO DE DE-PARA E AUDITORIA DE FROTAS</h1>
                
                <div class="cards-topo">
                    <div class="card-destaque" style="border-left: 4px solid #38bdf8;">
                        <div class="label-card">📅 Data em Evidência no Filtro</div>
                        <div class="valor-card">{data_formato_br}</div>
                    </div>
                    <div class="card-destaque" style="border-left: 4px solid #10b981;">
                        <div class="label-card">🕒 Última Extração da Base</div>
                        <div class="valor-hora">{horario_atualizacao}</div>
                    </div>
                </div>

                <div class="barra-filtros">
                    <form method="GET" action="/auditoria_depara" style="display: flex; align-items: center; width: 100%;">
                        <label>Alterar Data Operacional:</label>
                        <input type="date" name="data_filter_input" id="campoDataFiltro" value="{data_selecionada_iso}">
                        <button type="submit" class="btn-filtrar">🔍 Buscar Notas</button>
                    </form>
                </div>

                <div class="tabela-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>NF</th><th>EMISSÃO</th><th>CLIENTE</th><th>TRANSPORTADORA ORIGINAL</th><th>MODAL ATUAL</th><th>VALOR BRUTO</th><th style="color:#10b981;">AÇÃO DE ATUALIZAÇÃO (SALVA NA BASE)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {linhas_html}
                        </tbody>
                    </table>
                </div>
            </div>

            <script>
                // Força a sincronização do input e submete automaticamente ao mudar o calendário
                document.getElementById('campoDataFiltro').addEventListener('change', function() {{
                    // Altera o name dinamicamente para bater com o esperado na URL do Flask
                    this.name = "data_filtro";
                    this.form.submit();
                }});
            </script>
        </body>
        </html>
        """
        # Proteção extra para garantir que o parâmetro não se perca na requisição GET inicial
        return html.replace('name="data_filter_input"', 'name="data_filter_input"')
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return f"<h2>❌ Erro no painel de de-para: {str(e)}</h2>"
    
@app.route('/tv_devolucoes', methods=['GET'])
def tv_devolucoes():
    """Tela de devoluções para painéis TV (acesso público para monitores)."""
    return render_template('devolucao.html', transportadoras=ler_transportadoras_db())
    
# ============================================================
# ⚡ 4. MÓDULO DE DEVOLUÇÕES (HISTÓRICO OPERACIONAL E BUSCA DUPLA)
# ============================================================
# ============================================================
# ⚡ 4. MÓDULO DE DEVOLUÇÕES (HISTÓRICO OPERACIONAL - AJUSTADO)
# ============================================================
@app.route('/devolucao', methods=['GET'])
def tela_devolucoes():
    """Renderiza a interface mestre de lançamento de devoluções dentro do iframe central."""
    if 'usuario_id' not in session:
        return redirect('/login')
    return render_template('devolucao.html', transportadoras=ler_transportadoras_db())


@app.route('/api/salvar_devolucao', methods=['POST'])
@login_requerido()
def api_salvar_devolucao():
    """Insere uma nova ocorrência sequencial independente ou edita uma existente por ID."""
    import sqlite3
    from datetime import datetime

    try:
        dados = request.get_json() or {}
        id_reg = _id_str(dados.get('id'))  
        nf = str(dados.get('nota_fiscal', '')).lstrip('0').strip()
        data_dev = dados.get('data_devolucao', '').strip()
        transportadora = dados.get('transportadora', '').strip()
        ocorrencia = dados.get('ocorrencia', '').strip()
        cte = dados.get('cte_devolucao', '').strip()
        responsavel = dados.get('responsavel_recebimento', '').strip()
        detalhes = dados.get('detalhes_livre', '').strip()
        
        # 🆕 NOVOS CAMPOS OPERACIONAIS E SUPORTE A IMAGEM
        nome_recebedor = dados.get('nome_recebedor', '').strip()
        nota_devolucao_cliente = dados.get('nota_devolucao_cliente', '').strip()
        imagem_base64 = dados.get('imagem_base64', '').strip()

        if not nf or not data_dev or not ocorrencia:
            return jsonify({"status": "erro", "mensagem": "NF, Data e Ocorrência são obrigatórios!"}), 400

        if "-" in data_dev:
            try: data_dev = datetime.strptime(data_dev, '%Y-%m-%d').strftime('%d/%m/%Y')
            except: pass

        conn = get_db_connection()
        cursor = conn.cursor()

        # Garante a existência da tabela atualizada com suporte às novas mídias e campos
        if database_adapter.is_sqlite():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devolucoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nota_fiscal TEXT NOT NULL,
                    data_devolucao TEXT NOT NULL,
                    transportadora TEXT,
                    ocorrencia TEXT NOT NULL,
                    cte_devolucao TEXT,
                    responsavel_recebimento TEXT,
                    detalhes_livre TEXT,
                    nome_recebedor TEXT,
                    nota_devolucao_cliente TEXT,
                    imagem_base64 TEXT
                )
            """)

        # 🛡️ BLINDAGEM AUTOMÁTICA DE COLUNAS: Garante o transplante se a tabela local for antiga
        for coluna in ([] if database_adapter.is_sqlserver() else ['nome_recebedor', 'nota_devolucao_cliente', 'imagem_base64']):
            try:
                cursor.execute(f"ALTER TABLE devolucoes ADD COLUMN {coluna} TEXT")
            except sqlite3.OperationalError:
                pass  # Coluna já existe no computador local, ignora de forma segura

        if id_reg:
            # 🎯 MODO EDIÇÃO: Altera estritamente a linha do ID focado na devolução
            cursor.execute("""
                UPDATE devolucoes SET 
                    nota_fiscal = ?, data_devolucao = ?, transportadora = ?, ocorrencia = ?, 
                    cte_devolucao = ?, responsavel_recebimento = ?, detalhes_livre = ?,
                    nome_recebedor = ?, nota_devolucao_cliente = ?, imagem_base64 = ?
                WHERE id = ?
            """, (nf, data_dev, transportadora, ocorrencia, cte, responsavel, detalhes, nome_recebedor, nota_devolucao_cliente, imagem_base64, id_reg))
            msg_final = f"Registro de devolução ID {id_reg} atualizado com sucesso!"
        else:
            # 🎯 MODO NOVO REGISTRO: Gera uma NOVA LINHA livre, aceitando repetições de NF de forma histórica
            cursor.execute("""
                INSERT INTO devolucoes (nota_fiscal, data_devolucao, transportadora, ocorrencia, cte_devolucao, responsavel_recebimento, detalhes_livre, nome_recebedor, nota_devolucao_cliente, imagem_base64)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (nf, data_dev, transportadora, ocorrencia, cte, responsavel, detalhes, nome_recebedor, nota_devolucao_cliente, imagem_base64))
            msg_final = f"Nova ocorrência de devolução para a NF {nf} inserida no histórico!"

        # Crava na tabela geral de status consolidado como DEVOLVIDO sem duplicar valores nas views do carrossel
        texto_assinatura_obs = f"CTE DEV: {cte} | NOTA DEV CLI: {nota_devolucao_cliente} | {ocorrencia}"
        upsert_entrega_efetuada(
            cursor,
            nf,
            data_dev,
            f"DEV: {nome_recebedor.upper()}",
            texto_assinatura_obs,
        )

        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": msg_final})
    except Exception as e: return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route('/api/listar_devolucoes', methods=['GET'])
@login_requerido()
def api_listar_devolucoes():
    """Busca o histórico sequencial aplicando filtros combinados de NF e Cliente para o Grid."""
    import sqlite3

    filtro_nota = request.args.get('nota', '').strip()
    filtro_cliente = request.args.get('cliente', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Faz o sub-select limpo para buscar a razão social da tabela faturamento
    query = """
        SELECT d.*, f.cliente as cliente_faturamento
        FROM devolucoes d
        LEFT JOIN faturamento f ON TRIM(f.nf) = TRIM(d.nota_fiscal)
        WHERE 1=1
    """
    params = []

    if filtro_nota:
        query += " AND d.nota_fiscal LIKE ?"; params.append(f"%{filtro_nota}%")
    if filtro_cliente:
        query += " AND d.nota_fiscal IN (SELECT nf FROM faturamento WHERE cliente LIKE ?)"
        params.append(f"%{filtro_cliente}%")

    query += " ORDER BY d.id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    resultado = []
    for r in rows:
        chaves = r.keys()
        # Garante retrocompatibilidade para linhas salvas no passado sem as novas colunas
        val_recebedor = r["nome_recebedor"] if "nome_recebedor" in chaves and r["nome_recebedor"] else "-"
        val_nota_cli = r["nota_devolucao_cliente"] if "nota_devolucao_cliente" in chaves and r["nota_devolucao_cliente"] else "-"
        val_imagem = r["imagem_base64"] if "imagem_base64" in chaves and r["imagem_base64"] else ""

        resultado.append({
            "id": r["id"], 
            "nota_fiscal": r["nota_fiscal"], 
            "data_devolucao": r["data_devolucao"], 
            "transportadora": r["transportadora"],
            "ocorrencia": r["ocorrencia"], 
            "cte_devolucao": r["cte_devolucao"] if r["cte_devolucao"] else "-",
            "responsavel_recebimento": r["responsavel_recebimento"] if r["responsavel_recebimento"] else "-", 
            "detalhes_livre": r["detalhes_livre"], 
            "cliente_faturamento": r["cliente_faturamento"] if r["cliente_faturamento"] else "Não Localizado no Faturamento",
            "nome_recebedor": val_recebedor,
            "nota_devolucao_cliente": val_nota_cli,
            "imagem_base64": val_imagem
        })
    return jsonify(resultado)

@app.route('/api/excluir_devolucao', methods=['POST'])
@login_requerido()
def api_excluir_devolucao():
    """Remove permanentemente o registro de devolução física pelo ID e limpa o status cruzado."""
    import sqlite3
    from flask import request, jsonify

    try:
        dados = request.get_json() or {}
        id_reg = dados.get('id')
        nf = str(dados.get('nota_fiscal', '')).lstrip('0').strip()

        if not id_reg:
            return jsonify({"status": "erro", "mensagem": "ID do registro inválido para exclusão!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Deleta a ocorrência específica selecionada na tabela devolucoes
        cursor.execute("DELETE FROM devolucoes WHERE id = ?", (id_reg,))

        # 2. Verifica se a mesma Nota Fiscal ainda possui outras devoluções restantes no histórico
        cursor.execute("SELECT id FROM devolucoes WHERE nota_fiscal = ?", (nf,))
        outro_registro = cursor.fetchone()

        if not outro_registro:
            # Se não houver mais nenhum histórico, limpa a baixa na tabela mestre restaurando o status original
            cursor.execute("DELETE FROM entregas_efetuadas WHERE nota_fiscal = ?", (nf,))

        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": f"Ocorrência de devolução da NF {nf} excluída com sucesso!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": f"Erro interno ao deletar: {str(e)}"}), 500

# ============================================================
# ⚡ 5. GERENCIADOR INTEGRADO DE TRANSPORTADORAS (GRID NATIVO CORRIGIDO)
# ============================================================
@app.route('/gerenciar_transportadoras', methods=['GET'])
def gerenciar_transportadoras():
    """Renderiza a interface mestre de manutenção de transportadoras."""
    return render_template('gerenciar_transportadoras.html')


@app.route('/api/listar_transportadoras_gerenciador', methods=['GET'])
@login_requerido()
def api_listar_transportadoras_gerenciador():
    """Busca TODAS as transportadoras cadastradas blindando contra falta de colunas antigas."""
    import sqlite3
    from flask import request, jsonify
    
    busca = request.args.get('busca', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    if database_adapter.is_sqlserver():
        if busca:
            cursor.execute("""
                SELECT id, name, telephone, responsavel
                FROM transportadoras
                WHERE name LIKE ?
                ORDER BY name ASC
            """, (f"%{busca}%",))
        else:
            cursor.execute("SELECT id, name, telephone, responsavel FROM transportadoras ORDER BY name ASC")

        rows = cursor.fetchall()
        conn.close()
        return jsonify([{
            "id": r["id"],
            "name": r["name"],
            "telephone": r["telephone"] if r["telephone"] else "",
            "responsavel": r["responsavel"] if r["responsavel"] else ""
        } for r in rows])

    # 🛡️ BLINDAGEM COMPULSÓRIA: Tenta injetar as colunas direto na tabela física antes do SELECT
    try:
        cursor.execute("ALTER TABLE transportadoras ADD COLUMN telephone TEXT")
    except sqlite3.OperationalError:
        pass  # Se já existir, ignora o erro com segurança

    try:
        cursor.execute("ALTER TABLE transportadoras ADD COLUMN responsavel TEXT")
    except sqlite3.OperationalError:
        pass  # Se já existir, ignora o erro com segurança

    conn.commit() # Grava a estrutura nova no arquivo físico .db

    # Agora o banco está 100% pronto para rodar o SELECT com as 4 colunas sem dar erro!
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if busca:
        cursor.execute("""
            SELECT id, name, telephone, responsavel 
            FROM transportadoras 
            WHERE name LIKE ? 
            ORDER BY name ASC
        """, (f"%{busca}%",))
    else:
        cursor.execute("SELECT id, name, telephone, responsavel FROM transportadoras ORDER BY name ASC")
        
    rows = cursor.fetchall()
    conn.close()

    resultado = []
    for r in rows:
        resultado.append({
            "id": r["id"],
            "name": r["name"],
            "telephone": r["telephone"] if r["telephone"] else "",
            "responsavel": r["responsavel"] if r["responsavel"] else ""
        })

    return jsonify(resultado)


@app.route('/api/salvar_transportadora_gerenciador', methods=['POST'])
@login_requerido()
def api_salvar_transportadora_gerenciador():
    """Efetua a inclusão de uma nova transportadora ou atualiza uma existente via ID."""
    import sqlite3
    from flask import request, jsonify
    try:
        dados = request.get_json() or {}
        id_reg = _id_str(dados.get('id'))
        nome = str(dados.get('name', '')).strip().upper()
        tel = dados.get('telephone', '').strip()
        resp = dados.get('responsavel', '').strip()

        if not nome:
            return jsonify({"status": "erro", "mensagem": "O nome da transportadora é obrigatório!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        if id_reg:
            # MODO ATUALIZAÇÃO: Altera os dados mantendo o ID original
            cursor.execute("""
                UPDATE transportadoras 
                SET name = ?, telephone = ?, responsavel = ? 
                WHERE id = ?
            """, (nome, tel, resp, id_reg))
            msg = f"Transportadora {nome} atualizada com sucesso!"
        else:
            # MODO INCLUSÃO: Evita duplicar nomes iguais na lista
            cursor.execute("SELECT id FROM transportadoras WHERE name = ?", (nome,))
            if cursor.fetchone():
                conn.close()
                return jsonify({"status": "erro", "mensagem": f"A transportadora '{nome}' já está listada!"}), 400

            cursor.execute("""
                INSERT INTO transportadoras (name, telephone, responsavel) 
                VALUES (?, ?, ?)
            """, (nome, tel, resp))
            msg = f"Transportadora {nome} incluída com sucesso!"

        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": msg})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route('/api/excluir_transportadora_gerenciador', methods=['POST'])
@login_requerido()
def api_excluir_transportadora_gerenciador():
    """Remove a transportadora selecionada direto do Grid e da base de dados."""
    import sqlite3
    from flask import request, jsonify
    try:
        dados = request.get_json() or {}
        id_reg = dados.get('id')

        if not id_reg:
            return jsonify({"status": "erro", "mensagem": "ID inválido!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transportadoras WHERE id = ?", (id_reg,))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "sucesso", "mensagem": "Transportadora removida do cadastro mestre!"})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
    # ============================================================
# ⚡ 6. CENTRAL MESTRE DE DOCUMENTAÇÃO E MANUAL DO USUÁRIO
# ============================================================
@app.route('/manual', methods=['GET'])
def tela_manual_usuario():
    """Disponibiliza o manual do usuário estruturado via localhost."""
    return render_template('manual.html')

# ============================================================
# ⚡ 7. MÓDULO GESTOR DE E-MAILS (TRIAGEM, ASSUNTO E TRATATIVAS)
# ============================================================
@app.route('/gestor_emails', methods=['GET'])
def tela_gestor_emails():
    """Renderiza a interface mestre de gerenciamento e triagem de e-mails."""
    return render_template('gestor_emails.html')


@app.route('/api/salvar_email_gestor', methods=['POST'])
@login_requerido()
def api_salvar_email_gestor():
    """Grava um novo e-mail triado ou atualiza as ações operacionais tomadas por ID."""
    import sqlite3
    from flask import request, jsonify
    from datetime import datetime

    try:
        dados = request.get_json() or {}
        id_reg = _id_str(dados.get('id'))
        remetente = dados.get('remetente', '').strip()
        assunto = dados.get('assunto', '').strip()
        status = dados.get('status', 'PENDENTE').strip()
        conteudo = dados.get('conteudo_email', '').strip()
        acoes = dados.get('acoes_tomadas', '').strip()

        if not remetente or not assunto:
            return jsonify({"status": "erro", "mensagem": "Remetente e Assunto são obrigatórios!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Garante a criação estrutural da tabela dedicada de e-mails
        if database_adapter.is_sqlserver():
            agora = datetime.now().strftime('%d/%m/%Y %H:%M')
            if id_reg:
                cursor.execute("""
                    UPDATE gestor_emails SET
                        remetente = ?, assunto = ?, conteudo_email = ?, acoes_tomadas = ?, status = ?
                    WHERE id = ?
                """, (remetente, assunto, conteudo, acoes, status, id_reg))
                msg = "Tratativa de e-mail atualizada com sucesso no histÃ³rico!"
            else:
                cursor.execute("""
                    INSERT INTO gestor_emails (data_hora, remetente, assunto, conteudo_email, acoes_tomadas, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (agora, remetente, assunto, conteudo, acoes, status))
                msg = "E-mail importado e registrado com sucesso para monitoramento!"
            conn.commit()
            conn.close()
            return jsonify({"status": "sucesso", "mensagem": msg})

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gestor_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_hora TEXT NOT NULL,
                remetente TEXT NOT NULL,
                assunto TEXT NOT NULL,
                conteudo_email TEXT,
                acoes_tomadas TEXT,
                status TEXT NOT NULL
            )
        """)

        agora = datetime.now().strftime('%d/%m/%Y %H:%M')

        if id_reg:
            # 🎯 MODO ATUALIZAÇÃO: Grava a alteração do status e as novas ações tomadas
            cursor.execute("""
                UPDATE gestor_emails SET 
                    remetente = ?, assunto = ?, conteudo_email = ?, acoes_tomadas = ?, status = ?
                WHERE id = ?
            """, (remetente, assunto, conteudo, acoes, status, id_reg))
            msg = "Tratativa de e-mail atualizada com sucesso no histórico!"
        else:
            # 🎯 MODO INCLUSÃO: Insere um novo e-mail para triagem cronológica
            cursor.execute("""
                INSERT INTO gestor_emails (data_hora, remetente, assunto, conteudo_email, acoes_tomadas, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (agora, remetente, assunto, conteudo, acoes, status))
            msg = "E-mail importado e registrado com sucesso para monitoramento!"

        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": msg})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500


@app.route('/api/listar_emails_gestor', methods=['GET'])
@login_requerido()
def api_listar_emails_gestor():
    """Busca o histórico aplicando filtros combinados de assunto, remetente e status."""
    import sqlite3
    from flask import request, jsonify

    f_assunto = request.args.get('assunto', '').strip()
    f_remetente = request.args.get('remetente', '').strip()
    f_status = request.args.get('status', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    if database_adapter.is_sqlserver():
        query = "SELECT * FROM gestor_emails WHERE 1=1"
        params = []

        if f_assunto:
            query += " AND assunto LIKE ?"
            params.append(f"%{f_assunto}%")
        if f_remetente:
            query += " AND remetente LIKE ?"
            params.append(f"%{f_remetente}%")
        if f_status:
            query += " AND status = ?"
            params.append(f_status)

        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return jsonify([{
            "id": r["id"],
            "data_hora": r["data_hora"],
            "remetente": r["remetente"],
            "assunto": r["assunto"],
            "conteudo_email": r["conteudo_email"],
            "acoes_tomadas": r["acoes_tomadas"],
            "status": r["status"]
        } for r in rows])

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gestor_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT NOT NULL,
            remetente TEXT NOT NULL,
            assunto TEXT NOT NULL,
            conteudo_email TEXT,
            acoes_tomadas TEXT,
            status TEXT NOT NULL
        )
    """)

    query = "SELECT * FROM gestor_emails WHERE 1=1"
    params = []

    if f_assunto:
        query += " AND assunto LIKE ?"
        params.append(f"%{f_assunto}%")
    if f_remetente:
        query += " AND remetente LIKE ?"
        params.append(f"%{f_remetente}%")
    if f_status:
        query += " AND status = ?"
        params.append(f_status)

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    resultado = []
    for r in rows:
        resultado.append({
            "id": r["id"],
            "data_hora": r["data_hora"],
            "remetente": r["remetente"],
            "assunto": r["assunto"],
            "conteudo_email": r["conteudo_email"],
            "acoes_tomadas": r["acoes_tomadas"],
            "status": r["status"]
        })

    return jsonify(resultado)

# ============================================================
# ⚡ 8. SEGUNDA ROTA: VIEW LOCAL EXCLUSIVA PARA O NAVEGADOR
# ============================================================
@app.route('/relatorio_faturamento_local', methods=['GET'])
def relatorio_faturamento_local():
    """Rota espelho 100% blindada que herda a lógica original e aponta para o template local."""
    import sqlite3
    import pandas as pd
    from flask import request, render_template

    filtro_inicio = request.args.get('data_inicio', '').strip()
    filtro_fim = request.args.get('data_fim', '').strip()
    filtro_nf = request.args.get('busca_nf', '').strip()
    filtro_cliente = request.args.get('busca_cliente', '').strip()
    filtro_transp = request.args.get('busca_transp', '').strip()
    busca_status = request.args.get('busca_status', '').strip()
    
    pagina = request.args.get('page', 1, type=int)
    registros_por_pagina = 100
    offset = (pagina - 1) * registros_por_pagina

    # Reaproveita a exata rotina de sincronização de arquivos do seu motor
    excel_fat = buscar_ultimo_faturamento()
    if excel_fat:
        try: importar_faturamento_para_sqlite(excel_fat)
        except Exception as e: print(f"Aviso de sincronia faturamento local: {e}")

    dict_expedidas_relatorio = {}
    excel_exp = buscar_ultima_expedicao()
    if excel_exp:
        try:
            df_exp = pd.read_excel(excel_exp)
            if not df_exp.empty:
                df_exp, col_nf_v, col_data_v = normalizar_dataframe_expedicao(df_exp)
                for _, r in df_exp.iterrows():
                    nf_str_exp = str(r[col_nf_v]).strip()
                    if nf_str_exp and nf_str_exp not in ('nan', 'None', '-'):
                        dict_expedidas_relatorio[nf_str_exp] = {
                            "data_expedicao": str(r[col_data_v]).split()[0] if pd.notna(r[col_data_v]) else "-"
                        }
        except Exception as e:
            print(f"❌ Erro ao mapear arquivo de expedição local: {e}")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM faturamento")
    total_geral_faturadas = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM entregas_efetuadas")
    total_geral_entregues_db = cursor.fetchone()[0] or 0

    where_clauses = ["1=1"]
    params = []

    if filtro_cliente:
        where_clauses.append("f.cliente LIKE ?")
        params.append(f'%{filtro_cliente}%')
    if filtro_nf:
        where_clauses.append("f.nf LIKE ?")
        params.append(f'%{filtro_nf}%')
    if filtro_transp:
        where_clauses.append("f.transportadora LIKE ?")
        params.append(f'%{filtro_transp}%')
    if filtro_inicio:
        where_clauses.append("f.emissao >= ?")
        params.append(filtro_inicio)
    if filtro_fim:
        where_clauses.append("f.emissao <= ?")
        params.append(filtro_fim)

    where_str = " AND ".join(where_clauses)

    group_by_nf = "" if database_adapter.is_sqlserver() else "GROUP BY f.nf"
    query_dados_total = f"""
        SELECT 
            f.nf AS [Nota Fiscal], f.emissao AS [Emissão], f.cliente AS [Cliente], 
            f.endereco AS [Endereço], f.municipio AS [Município], f.uf AS [UF], f.cep AS [CEP], 
            f.transportadora AS [Transportadora], f.modalidade AS [Modalidade], f.volumes AS [Volumes], 
            f.especie AS [Espécie], f.peso_bruto_nf AS [Peso Bruto], f.pedido AS [Pedido], 
            f.valor_total_nf AS [Valor Total], e.data_entrega AS [Data Entrega], 
            e.recebedor AS [Recebedor], e.assinatura AS [Assinatura / Obs] 
        FROM faturamento f 
        LEFT JOIN entregas_efetuadas e ON f.nf = e.nota_fiscal 
        WHERE {where_str} 
        {group_by_nf}
        ORDER BY f.nf DESC
    """
    
    cursor.execute(query_dados_total, params)
    rows_completas = cursor.fetchall()
    conn.close()

    dados_filtrados_com_status = []
    total_expedidas_filtro = 0
    total_entregues_filtro = 0
    total_nao_exp_filtro = 0
    valor_total_filtro = 0.0

    for r in rows_completas:
        item = dict(r)
        nf_str = str(item['Nota Fiscal']).strip()
        val_raw = str(item['Valor Total']).replace('R$', '').strip()
        
        if ',' in val_raw and '.' in val_raw:
            val_limpo = val_raw.replace('.', '').replace(',', '.')
        elif ',' in val_raw:
            val_limpo = val_raw.replace(',', '.')
        else:
            val_limpo = val_raw

        try: val_float = float(val_limpo)
        except Exception: val_float = 0.0

        info_exp_combinada = dict_expedidas_relatorio.get(nf_str, None)

        if item.get('Data Entrega') and item['Data Entrega'] not in ('', '-', None):
            status_final = 'ENTREGUE'
            total_entregues_filtro += 1
            item['Data Expedição'] = info_exp_combinada['data_expedicao'] if info_exp_combinada else "-"
            item['data_expedicao'] = info_exp_combinada['data_expedicao'] if info_exp_combinada else "-"
        elif info_exp_combinada is not None:
            status_final = 'EXPEDIDO'
            total_expedidas_filtro += 1
            item['Data Expedição'] = info_exp_combinada['data_expedicao']
            item['data_expedicao'] = info_exp_combinada['data_expedicao']
        else:
            status_final = 'NÃO EXPEDIDO'
            total_nao_exp_filtro += 1
            item['Data Expedição'] = "-"
            item['data_expedicao'] = "-"

        item['STATUS EXPEDIÇÃO'] = status_final

        if busca_status and status_final != busca_status:
            continue
            
        valor_total_filtro += val_float
        dados_filtrados_com_status.append(item)

    total_faturadas_filtro = len(dados_filtrados_com_status)
    financeiro_filtrado = round(valor_total_filtro, 2)
    
    total_geral_movimentadas = total_geral_entregues_db
    total_geral_em_aberto_recalculado = max(0, total_geral_faturadas - total_geral_movimentadas)
    taxa_eficiencia = round((total_geral_movimentadas / total_geral_faturadas * 100), 1) if total_geral_faturadas > 0 else 0.0

    dados_lista_paginada = dados_filtrados_com_status[offset : offset + registros_por_pagina]

    colunas = [
        'Nota Fiscal', 'Emissão', 'Cliente', 'Endereço', 'Município', 'UF', 'CEP',
        'Transportadora', 'Modalidade', 'Volumes', 'Espécie', 'Peso Bruto', 'Pedido',
        'Valor Total', 'STATUS EXPEDIÇÃO', 'Data Expedição', 'Data Entrega', 'Recebedor', 'Assinatura / Obs'
    ]

    # 🎯 APONTAMENTO SEGURO: Renderiza estritamente o arquivo com o sufixo "_local"
    return render_template(
        'relatorio_faturamento_local.html', dados=dados_lista_paginada, colunas=colunas,
        filtro_nf=filtro_nf, filtro_cliente=filtro_cliente, filtro_transp=filtro_transp,
        busca_status=busca_status, data_inicio=filtro_inicio, data_fim=filtro_fim,
        total_faturadas=total_geral_faturadas, total_expedidas=total_geral_movimentadas,
        total_em_aberto=total_geral_em_aberto_recalculado, taxa_eficiencia=taxa_eficiencia,
        total_faturadas_filtro=total_faturadas_filtro, total_expedidas_filtro=total_expedidas_filtro,
        total_em_aberto_filtro=total_nao_exp_filtro,
        financeiro_filtrado=f"R$ {financeiro_filtrado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        page=pagina, tem_mais=(len(dados_filtrados_com_status) > offset + registros_por_pagina), erro=None
    )

# ============================================================
# LOGIN, PORTAL E CONTROLE DE ACESSO
# ============================================================

def _custos_hoje():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _custos_to_float(valor):
    texto = str(valor or '0').strip().replace('.', '').replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _custos_add_months(data_iso, meses, dia_preferido=None):
    base = datetime.strptime(data_iso, '%Y-%m-%d')
    mes_alvo = base.month - 1 + int(meses)
    ano = base.year + mes_alvo // 12
    mes = mes_alvo % 12 + 1
    dia = int(dia_preferido or base.day)
    dia = min(dia, calendar.monthrange(ano, mes)[1])
    return datetime(ano, mes, dia).strftime('%Y-%m-%d')


def _custos_lookup_nome(tabela, nome):
    nome_limpo = str(nome or '').strip()
    if not nome_limpo:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"INSERT OR IGNORE INTO {tabela} (nome, criado_em) VALUES (?, ?)", (nome_limpo, _custos_hoje()))
    cur.execute(f"SELECT id FROM {tabela} WHERE nome = ?", (nome_limpo,))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else None


def _custos_lista_opcoes(conn, tabela):
    return [dict(r) for r in conn.execute(
        f"SELECT id, nome FROM {tabela} WHERE ativo = 1 ORDER BY nome"
    ).fetchall()]


@app.route('/custos_pessoais', methods=['GET'])
def custos_pessoais():
    return render_template('custos_pessoais.html')


@app.route('/api/custos/opcoes', methods=['GET'])
def api_custos_opcoes():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    dados = {
        'tipos': _custos_lista_opcoes(conn, 'custos_tipos_despesa'),
        'origens': _custos_lista_opcoes(conn, 'custos_origens'),
        'pessoas': _custos_lista_opcoes(conn, 'custos_pessoas'),
    }
    conn.close()
    return jsonify(dados)


@app.route('/api/custos/cadastrar_base', methods=['POST'])
def api_custos_cadastrar_base():
    dados = request.get_json(silent=True) or {}
    mapa = {'tipo': 'custos_tipos_despesa', 'origem': 'custos_origens', 'pessoa': 'custos_pessoas'}
    tabela = mapa.get(dados.get('base'))
    nome = str(dados.get('nome') or '').strip()
    if not tabela or not nome:
        return jsonify({'ok': False, 'erro': 'Informe a base e o nome.'}), 400
    item_id = _custos_lookup_nome(tabela, nome)
    return jsonify({'ok': True, 'id': item_id})


@app.route('/api/custos/lancamentos', methods=['GET'])
def api_custos_lancamentos():
    filtros = []
    params = []
    if request.args.get('tipo_despesa_id'):
        filtros.append('l.tipo_despesa_id = ?')
        params.append(request.args.get('tipo_despesa_id'))
    if request.args.get('pessoa_id'):
        filtros.append('l.pessoa_id = ?')
        params.append(request.args.get('pessoa_id'))
    if request.args.get('data_inicio'):
        filtros.append("COALESCE(l.data_prevista_pagamento, l.data_lancamento) >= ?")
        params.append(request.args.get('data_inicio'))
    if request.args.get('data_fim'):
        filtros.append("COALESCE(l.data_prevista_pagamento, l.data_lancamento) <= ?")
        params.append(request.args.get('data_fim'))
    where = ('WHERE ' + ' AND '.join(filtros)) if filtros else ''

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    sql = f"""
        SELECT l.*, t.nome AS tipo_despesa, o.nome AS origem, p.nome AS pessoa,
               substr(COALESCE(l.data_prevista_pagamento, l.data_lancamento), 1, 7) AS periodo
        FROM custos_lancamentos l
        LEFT JOIN custos_tipos_despesa t ON t.id = l.tipo_despesa_id
        LEFT JOIN custos_origens o ON o.id = l.origem_id
        LEFT JOIN custos_pessoas p ON p.id = l.pessoa_id
        {where}
        ORDER BY COALESCE(l.data_prevista_pagamento, l.data_lancamento), l.id DESC
    """
    lancamentos = [dict(r) for r in conn.execute(sql, params).fetchall()]
    resumo = {'despesas': 0.0, 'creditos': 0.0, 'saldo': 0.0, 'por_mes': []}
    por_mes = {}
    for item in lancamentos:
        mes = item['periodo'] or 'Sem periodo'
        por_mes.setdefault(mes, {'periodo': mes, 'despesas': 0.0, 'creditos': 0.0, 'saldo': 0.0})
        valor = float(item['valor'] or 0)
        if item['tipo_movimento'] == 'credito':
            resumo['creditos'] += valor
            por_mes[mes]['creditos'] += valor
        else:
            resumo['despesas'] += valor
            por_mes[mes]['despesas'] += valor
    resumo['saldo'] = resumo['creditos'] - resumo['despesas']
    for mes in por_mes.values():
        mes['saldo'] = mes['creditos'] - mes['despesas']
    resumo['por_mes'] = list(por_mes.values())
    conn.close()
    return jsonify({'lancamentos': lancamentos, 'resumo': resumo})


@app.route('/api/custos/lancamentos', methods=['POST'])
def api_custos_salvar_lancamento():
    dados = request.get_json(silent=True) or {}
    descricao = str(dados.get('descricao') or '').strip()
    tipo_movimento = dados.get('tipo_movimento') if dados.get('tipo_movimento') in ('despesa', 'credito') else 'despesa'
    valor_total = _custos_to_float(dados.get('valor_total'))
    data_lancamento = dados.get('data_lancamento') or datetime.now().strftime('%Y-%m-%d')
    data_prevista = dados.get('data_prevista_pagamento') or data_lancamento
    parcelas_total = max(1, int(dados.get('parcelas_total') or 1))
    if not descricao or valor_total <= 0:
        return jsonify({'ok': False, 'erro': 'Informe descricao e valor maior que zero.'}), 400

    grupo = f"CUSTO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}" if parcelas_total > 1 else None
    valor_parcela = round(valor_total / parcelas_total, 2)
    valores = [valor_parcela] * parcelas_total
    valores[-1] = round(valor_total - sum(valores[:-1]), 2)

    conn = get_db_connection()
    cur = conn.cursor()
    for idx, valor in enumerate(valores, start=1):
        vencimento = _custos_add_months(data_prevista, idx - 1)
        desc_parcela = f"{descricao} ({idx}/{parcelas_total})" if parcelas_total > 1 else descricao
        cur.execute("""
            INSERT INTO custos_lancamentos (
                grupo_parcelamento, tipo_movimento, descricao, tipo_despesa_id, origem_id, pessoa_id,
                valor, valor_total, data_lancamento, data_prevista_pagamento, parcela_numero,
                parcelas_total, observacao, status, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            grupo, tipo_movimento, desc_parcela, dados.get('tipo_despesa_id') or None,
            dados.get('origem_id') or None, dados.get('pessoa_id') or None, valor,
            valor_total, data_lancamento, vencimento, idx, parcelas_total,
            dados.get('observacao'), 'previsto', _custos_hoje(),
        ))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'parcelas_criadas': parcelas_total})


@app.route('/api/custos/agendamentos', methods=['GET', 'POST'])
def api_custos_agendamentos():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    if request.method == 'GET':
        linhas = [dict(r) for r in conn.execute("""
            SELECT a.*, t.nome AS tipo_despesa, o.nome AS origem, p.nome AS pessoa
            FROM custos_agendamentos a
            LEFT JOIN custos_tipos_despesa t ON t.id = a.tipo_despesa_id
            LEFT JOIN custos_origens o ON o.id = a.origem_id
            LEFT JOIN custos_pessoas p ON p.id = a.pessoa_id
            WHERE a.ativo = 1
            ORDER BY a.nome
        """).fetchall()]
        conn.close()
        return jsonify({'agendamentos': linhas})

    dados = request.get_json(silent=True) or {}
    nome = str(dados.get('nome') or '').strip()
    descricao = str(dados.get('descricao') or '').strip()
    valor_total = _custos_to_float(dados.get('valor_total'))
    dia = max(1, min(31, int(dados.get('dia_vencimento') or 1)))
    if not nome or not descricao or valor_total <= 0:
        conn.close()
        return jsonify({'ok': False, 'erro': 'Informe nome, descricao e valor.'}), 400
    conn.execute("""
        INSERT INTO custos_agendamentos (
            nome, tipo_movimento, descricao, tipo_despesa_id, origem_id, pessoa_id,
            valor_total, dia_vencimento, data_inicio, parcelas_total, observacao, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        nome, dados.get('tipo_movimento') if dados.get('tipo_movimento') in ('despesa', 'credito') else 'despesa',
        descricao, dados.get('tipo_despesa_id') or None, dados.get('origem_id') or None,
        dados.get('pessoa_id') or None, valor_total, dia,
        dados.get('data_inicio') or datetime.now().strftime('%Y-%m-%d'),
        max(1, int(dados.get('parcelas_total') or 1)), dados.get('observacao'), _custos_hoje(),
    ))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/custos/agendamentos/<int:agendamento_id>/lancar', methods=['POST'])
def api_custos_lancar_agendamento(agendamento_id):
    dados = request.get_json(silent=True) or {}
    meses = max(1, int(dados.get('meses') or 1))
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    ag = conn.execute("SELECT * FROM custos_agendamentos WHERE id = ? AND ativo = 1", (agendamento_id,)).fetchone()
    if not ag:
        conn.close()
        return jsonify({'ok': False, 'erro': 'Agendamento nao encontrado.'}), 404
    cur = conn.cursor()
    for idx in range(meses):
        vencimento = _custos_add_months(ag['data_inicio'], idx, ag['dia_vencimento'])
        cur.execute("""
            INSERT INTO custos_lancamentos (
                tipo_movimento, descricao, tipo_despesa_id, origem_id, pessoa_id,
                valor, valor_total, data_lancamento, data_prevista_pagamento,
                parcela_numero, parcelas_total, observacao, status, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, 'previsto', ?)
        """, (
            ag['tipo_movimento'], ag['descricao'], ag['tipo_despesa_id'], ag['origem_id'], ag['pessoa_id'],
            ag['valor_total'], ag['valor_total'], datetime.now().strftime('%Y-%m-%d'), vencimento,
            ag['observacao'], _custos_hoje(),
        ))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'lancamentos_criados': meses})


@app.route('/login', methods=['GET', 'POST'])
def tela_login_sistema():
    """Autenticação via banco de usuários."""
    import werkzeug.security as ws

    if request.method == 'POST':
        dados = request.get_json() or {}
        user_login = dados.get('login', '').strip()
        user_senha = dados.get('senha', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios_sistema WHERE login = ?", (user_login,))
        usuario = cursor.fetchone()
        conn.close()

        if usuario and ws.check_password_hash(usuario['senha_hash'], user_senha):
            _aplicar_sessao_usuario(usuario)
            registrar_log_operacional("LOGIN", f"Usuário {user_login} autenticado.")
            resp = make_response(jsonify({"status": "sucesso", "mensagem": "Acesso autorizado!"}))
            return _anexar_cookie_acesso_dia(resp, usuario)

        return jsonify({"status": "erro", "mensagem": "Usuário ou senha incorretos!"}), 401

    if 'usuario_id' in session:
        return redirect('/portal_operacional')
    if _ler_cookie_acesso_dia():
        return redirect('/portal_operacional')
    return render_template('login.html')


@app.route('/logout')
def logout_sistema():
    """Limpa a sessão e desloga o usuário."""
    registrar_log_operacional("LOGOUT", "Usuário encerrou a sessão de forma voluntária.")
    session.clear()
    resp = redirect('/login')
    resp.set_cookie(COOKIE_ACESSO_DIA, '', max_age=0, httponly=True, samesite='Lax')
    return resp


@app.route('/api/obter_missao', methods=['GET'])
def api_obter_missao():
    """Busca os dizeres horizontais salvos da missão."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM configuracoes_painel WHERE chave = 'missao'")
    res = cursor.fetchone()
    conn.close()
    return jsonify({"missao": res[0] if res else ""})


@app.route('/api/salvar_missao', methods=['POST'])
@login_requerido(['ADMIN', 'DIRETOR'])
def api_salvar_missao():
    """Atualiza os dizeres da faixa horizontal e registra quem alterou."""
    dados = request.get_json() or {}
    nova_frase = dados.get('missao', '').strip()
    
    if not nova_frase:
        return jsonify({"status": "erro", "mensagem": "A frase não pode ficar vazia!"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    if database_adapter.is_sqlserver():
        cursor.execute("SELECT chave FROM configuracoes_painel WHERE chave = 'missao'")
        if cursor.fetchone():
            cursor.execute("UPDATE configuracoes_painel SET valor = ? WHERE chave = 'missao'", (nova_frase,))
        else:
            cursor.execute("INSERT INTO configuracoes_painel (chave, valor) VALUES ('missao', ?)", (nova_frase,))
    else:
        cursor.execute("INSERT OR REPLACE INTO configuracoes_painel (chave, valor) VALUES ('missao', ?)", (nova_frase,))
    conn.commit()
    conn.close()
    
    registrar_log_operacional("ALTERAÇÃO DE MISSÃO", f"Nova frase gravada: {nova_frase}")
    return jsonify({"status": "sucesso", "mensagem": "Painel horizontal updated!"})


# ============================================================
# ⚡ 10. PORTAL MESTRE HORIZONTAL INDEPENDENTE (NAVEGADOR)
# ============================================================
@app.route('/portal_operacional', methods=['GET'])
def tela_portal_operacional_navegador():
    """Renderiza a máscara horizontal mestre (Portal de Controle)."""
    if 'usuario_id' not in session:
        return redirect('/login')
    return render_template('portal_operacional.html')


# ============================================================
# 🔒 CONTROLE RAIZ DE FLUXO (FECHAMENTO DE SPRINT OPERACIONAL)
# ============================================================
@app.route('/', methods=['GET'])
def portal_ignicao_login():
    """Porta da frente definitiva: Se já estiver logado, vai pro portal. Se não, tela de LOGIN."""
    if 'usuario_id' in session:
        return redirect('/portal_operacional')
    return render_template('login.html')


@app.route('/tela_boas_vindas', methods=['GET'])
def miolo_portal_boas_vindas():
    """Menu inicial com catálogo completo de módulos e links de rede."""
    if 'usuario_id' not in session:
        return redirect('/login')
    dados = montar_dados_catalogo_portal(obter_porta_atual())
    return render_template(
        'boas_vindas.html',
        catalogo=dados['catalogo'],
        enderecos=dados['enderecos'],
        links_rede=dados['links_rede'],
        porta=dados['porta'],
        ip_principal=dados['ip_principal'],
        usuario_nivel=session.get('usuario_nivel', 'SAC'),
    )


@app.route('/api/catalogo_portal', methods=['GET'])
@login_requerido()
def api_catalogo_portal():
    """Retorna catálogo de módulos e URLs completas por IP (JSON)."""
    dados = montar_dados_catalogo_portal(obter_porta_atual())
    return jsonify(dados)


@app.route('/abertura', methods=['GET'])
def redirecionamento_abertura_legado():
    """Redireciona chamadas legadas de roteamento com segurança para a nova estrutura."""
    return redirect('/tela_boas_vindas')


@app.route('/gerenciar_usuarios', methods=['GET'])
@login_requerido(['ADMIN'])
def tela_gerenciar_usuarios():
    """Renderiza a tela mestre de controle de usuários e permissões."""
    return render_template('usuarios.html')


@app.route('/api/listar_usuarios', methods=['GET'])
@login_requerido(['ADMIN'])
def api_listar_usuarios():
    """Retorna a lista de todos os usuários cadastrados no banco para o grid."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, login, nivel_hierarquico FROM usuarios_sistema ORDER BY nome ASC")
    rows = cursor.fetchall()
    conn.close()
    
    resultado = [{"id": r["id"], "nome": r["nome"], "login": r["login"], "nivel": r["nivel_hierarquico"]} for r in rows]
    return jsonify(resultado)


@app.route('/api/salvar_usuario', methods=['POST'])
@login_requerido(['ADMIN'])
def api_salvar_usuario():
    """Cadastra um novo operador com senha criptografada ou remove um perfil."""
    import werkzeug.security as ws

    try:
        dados = request.get_json() or {}
        acao = dados.get('acao', 'salvar')
        id_user = dados.get('id')
        nome = dados.get('nome', '').strip()
        login = dados.get('login', '').strip()
        senha = dados.get('senha', '').strip()
        nivel = dados.get('nivel', '').upper()

        conn = get_db_connection()
        cursor = conn.cursor()

        if acao == 'excluir':
            if str(id_user) == "1" or login == "admin":
                conn.close()
                return jsonify({"status": "erro", "mensagem": "O Administrador mestre do sistema não pode ser removido!"}), 400
            cursor.execute("DELETE FROM usuarios_sistema WHERE id = ?", (id_user,))
            msg = "Usuário revogado e removido do sistema com sucesso!"
            registrar_log_operacional("REVOGAÇÃO DE ACESSO", f"ID {id_user} removido.")
        else:
            if not nome or not login or not nivel:
                conn.close()
                return jsonify({"status": "erro", "mensagem": "Nome, Login e Nível são obrigatórios!"}), 400
            
            if id_user:
                if senha:
                    senha_hash = ws.generate_password_hash(senha)
                    cursor.execute("UPDATE usuarios_sistema SET nome=?, login=?, senha_hash=?, nivel_hierarquico=? WHERE id=?", (nome, login, senha_hash, nivel, id_user))
                else:
                    cursor.execute("UPDATE usuarios_sistema SET nome=?, login=?, nivel_hierarquico=? WHERE id=?", (nome, login, nivel, id_user))
                msg = f"Perfil de {nome} atualizado com sucesso!"
                registrar_log_operacional("ALTERAÇÃO DE PERFIL", f"Dados de {login} modificados.")
            else:
                if not senha:
                    conn.close()
                    return jsonify({"status": "erro", "mensagem": "Senha é obrigatória para novos usuários!"}), 400
                senha_hash = ws.generate_password_hash(senha)
                try:
                    cursor.execute("INSERT INTO usuarios_sistema (nome, login, senha_hash, nivel_hierarquico) VALUES (?, ?, ?, ?)", (nome, login, senha_hash, nivel))
                    msg = f"Novo usuário {nome} cadastrado com o nível {nivel}!"
                    registrar_log_operacional("CADASTRO DE USUÁRIO", f"Login {login} criado com nível {nivel}.")
                except sqlite3.IntegrityError:
                    conn.close()
                    return jsonify({"status": "erro", "mensagem": "Este Login já está sendo utilizado por outro operador!"}), 400

        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": msg})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
    # ============================================================
# 🧪 ROTAS AUXILIARES TEMPORÁRIAS PARA ADRIANO VISUALIZAR OS LAYOUTS
# ============================================================
@app.route('/teste_abas')
@login_requerido()
def teste_layout_abas():
    return render_template('portal_abas.html')

@app.route('/teste_lateral')
@login_requerido()
def teste_layout_lateral():
    return render_template('portal_lateral.html')

@app.route('/teste_blocos')
@login_requerido()
def teste_layout_blocos():
    return render_template('portal_blocos.html')

# ============================================================
# 🖼️ ROTAS EXCLUSIVAS DE IMAGENS OPERACIONAIS (ANTI-BLOQUEIO)
# ============================================================
@app.route('/cdn/logo_corax', methods=['GET'])
def servir_logo_corax():
    """Busca a logo da Corax local e serve para o iframe sem passar pela internet."""
    caminho = os.path.join(BASE_DIR, 'logo_corax.png')
    if os.path.exists(caminho):
        return send_file(caminho, mimetype='image/png')
    return "Remoto", 404

@app.route('/cdn/logo_ultrasafe', methods=['GET'])
def servir_logo_ultrasafe():
    """Busca a logo da Ultra Safe local e serve para o iframe sem passar pela internet."""
    caminho = os.path.join(BASE_DIR, 'logo_ultrasafe.png')
    if os.path.exists(caminho):
        return send_file(caminho, mimetype='image/png')
    return "Remoto", 404

# ============================================================
# 🎯 API EXCLUSIVA PARA ALIMENTAR A LISTA DE DEVOLUÇÕES
# ============================================================
@app.route('/api/obter_motivos_ocorrencias', methods=['GET'])
def api_obter_motivos_ocorrencias_viva():
    """Busca a lista de motivos direto da tabela do banco de dados e envia como JSON."""
    try:
        # Chama a função que já existe nas suas 3.500 linhas para ler o SQLite
        motivos = ler_motivos_ocorrencias_db()
        return jsonify(motivos)
    except Exception as e:
        print(f"❌ Erro na API de motivos para devolução: {e}")
        return jsonify([])
    
    import requests
import io
import pandas as pd
from datetime import datetime

# =====================================================================
# 📊 MÓDULO ADRIANO: PAINEL DE AUDITORIA EAN (VERSÃO ULTRA-ESTÁVEL)
# =====================================================================

@app.route('/gerenciar_ean')
@login_requerido()
def gerenciar_ean_tela_oficial():
    """Renderiza a página visual de gerenciamento de EAN"""
    return render_template('gerenciar_ean.html')

@app.route('/api/ean', methods=['GET'])
@login_requerido()
def api_listar_eans_oficial():
    """Lista todos os itens cadastrados coletando do histórico de faturamento"""
    busca = request.args.get('busca', '').strip()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if database_adapter.is_sqlite():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS de_para_ean (
                    codigo_item TEXT PRIMARY KEY,
                    descricao TEXT,
                    codigo_ean TEXT NOT NULL
                )
            """)
            conn.commit()

        if busca:
            cursor.execute("""
                SELECT fi.codigo_item, fi.descricao_item, COALESCE(e.codigo_ean, '') AS codigo_ean
                FROM faturamento_itens fi
                LEFT JOIN de_para_ean e ON TRIM(e.codigo_item) = TRIM(fi.codigo_item)
                WHERE fi.codigo_item IS NOT NULL
                  AND TRIM(fi.codigo_item) != ''
                  AND UPPER(TRIM(fi.codigo_item)) != 'NONE'
                  AND (
                    fi.codigo_item LIKE ?
                    OR fi.descricao_item LIKE ?
                    OR COALESCE(e.codigo_ean, '') LIKE ?
                  )
                ORDER BY fi.descricao_item ASC
            """, (f'%{busca}%', f'%{busca}%', f'%{busca}%'))
        else:
            cursor.execute("""
                SELECT fi.codigo_item, fi.descricao_item, COALESCE(e.codigo_ean, '') AS codigo_ean
                FROM faturamento_itens fi
                LEFT JOIN de_para_ean e ON TRIM(e.codigo_item) = TRIM(fi.codigo_item)
                WHERE fi.codigo_item IS NOT NULL
                  AND TRIM(fi.codigo_item) != ''
                  AND UPPER(TRIM(fi.codigo_item)) != 'NONE'
                ORDER BY fi.descricao_item ASC
            """)
            
        all_linhas = cursor.fetchall()
        conn.close()

        # 🎯 FILTRO INTELIGENTE NO PYTHON (Evita o erro do GROUP BY do SQLite)
        # Usamos um dicionário para garantir que cada código de item (ex: USA0120000VM) apareça uma única vez
        itens_unicos = {}
        cont_id = 1
        
        for r in all_linhas:
            cod_item = str(r[0]).strip()
            
            # Se já adicionamos esse produto na lista, pula para o próximo para não duplicar na tela
            if cod_item in itens_unicos:
                # Se o registro atual tiver um EAN populado e o anterior não, atualiza o EAN mestre
                if r[2] and str(r[2]).strip().upper() != 'NONE' and str(r[2]).strip() != '':
                    itens_unicos[cod_item]["codigo_ean"] = str(r[2]).strip()
                continue
                
            desc_item = str(r[1]).strip().upper() if r[1] else "- PRODUTO SEM DESCRIÇÃO -"
            raw_ean = str(r[2]).strip() if r[2] else ""
            cod_ean = raw_ean if (raw_ean.upper() != 'NONE' and raw_ean.upper() != 'NULL') else ""

            itens_unicos[cod_item] = {
                "id": cont_id,
                "codigo_item": cod_item,
                "descricao": desc_item,
                "codigo_ean": cod_ean
            }
            cont_id += 1

        # Transforma o dicionário de volta em uma lista para enviar para a tela
        lista_final = list(itens_unicos.values())
        return jsonify(lista_final), 200

    except Exception as e:
        print(f"❌ [ERRO CRÍTICO NO MÓDULO EAN]: {str(e)}")
        return jsonify({"status": "erro", "mensagem": f"Erro interno no banco: {str(e)}"}), 500

@app.route('/api/ean/salvar', methods=['POST'])
@login_requerido()
def api_salvar_ean_oficial():
    """Grava ou modifica o código EAN de um item em todas as tabelas do banco"""
    dados = request.get_json() or {}
    codigo_item = str(dados.get('codigo_item', '')).strip()
    descricao = str(dados.get('descricao', '')).upper().strip()
    codigo_ean = str(dados.get('codigo_ean', '')).strip()

    if not codigo_item or not codigo_ean:
        return jsonify({"status": "erro", "mensagem": "Código do Item e Código EAN são obrigatórios!"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if database_adapter.is_sqlite():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS de_para_ean (
                    codigo_item TEXT PRIMARY KEY,
                    descricao TEXT,
                    codigo_ean TEXT NOT NULL
                )
            """)
            cursor.execute("""
                INSERT INTO de_para_ean (codigo_item, descricao, codigo_ean)
                VALUES (?, ?, ?)
                ON CONFLICT(codigo_item) DO UPDATE SET
                    descricao = COALESCE(NULLIF(excluded.descricao, ''), de_para_ean.descricao),
                    codigo_ean = excluded.codigo_ean
            """, (codigo_item, descricao, codigo_ean))
        else:
            cursor.execute("SELECT codigo_item FROM de_para_ean WHERE codigo_item = ?", (codigo_item,))
            if cursor.fetchone():
                cursor.execute("""
                    UPDATE de_para_ean
                    SET descricao = COALESCE(NULLIF(?, ''), descricao), codigo_ean = ?
                    WHERE codigo_item = ?
                """, (descricao, codigo_ean, codigo_item))
            else:
                cursor.execute("""
                    INSERT INTO de_para_ean (codigo_item, descricao, codigo_ean)
                    VALUES (?, ?, ?)
                """, (codigo_item, descricao, codigo_ean))

        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": "EAN vinculado com sucesso!"}), 200
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500

@app.route('/api/ean/excluir/<string:codigo_item>', methods=['DELETE'])
@login_requerido()
def api_excluir_ean_oficial(codigo_item):
    """Remove o EAN associado ao item voltando o campo para nulo"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if database_adapter.is_sqlite():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS de_para_ean (
                    codigo_item TEXT PRIMARY KEY,
                    descricao TEXT,
                    codigo_ean TEXT NOT NULL
                )
            """)
        cursor.execute("DELETE FROM de_para_ean WHERE TRIM(codigo_item) = ?", (codigo_item.strip(),))
        conn.commit()
        conn.close()
        return jsonify({"status": "sucesso", "mensagem": "EAN removido com sucesso!"}), 200
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
# =====================================================================
# 📊 MÓDULO ADRIANO: MATRIZ CURVA ABC AUTOMÁTICA (DETECÇÃO DE TABELAS)
# =====================================================================

# # =====================================================================
# 📦 MÓDULO ADRIANO: FUNÇÕES AUXILIARES DE INVENTÁRIO DE ESTOQUE
# =====================================================================

def buscar_ultimo_estoque_downloads():
    """Varre a pasta de downloads do usuário Adriano e localiza a planilha de estoque mais recente"""
    import glob
    import os
    pasta_downloads = PASTA_DOWNLOADS
    padrao_arquivo = os.path.join(pasta_downloads, "posicao_estoque_empresa*.xls*")
    arquivos = glob.glob(padrao_arquivo)
    
    if not arquivos:
        return None
    return max(arquivos, key=os.path.getmtime)


# =====================================================================
# 📦 MÓDULO ADRIANO: ROTAS DO PAINEL INTEGRADO DE SALDO & GIRO
# =====================================================================

@app.route('/ver_estoque')
def painel_ver_estoque_adriano():
    """Renderiza a página visual avançada de Saldo de Estoque e Busca por Texto"""
    return render_template('ver_estoque.html')

@app.route('/curva_abc')
def painel_curva_abc():
    """Painel de curva ABC de estoque."""
    return render_template('curva_abc.html')

@app.route('/api/logistica/curva_abc', methods=['GET'])
def api_calcular_curva_abc_pareto_real():
    """MÓDULO ADRIANO - VERSÃO ULTRA BLINDADA CONSOLIDADA: Preserva 100% da inteligência
    do faturamento, Pareto e Corax, garantindo a exibição de itens inventariados novos."""
    try:
        import sqlite3
        import re
        from flask import request, jsonify
        
        mes_escolhido = request.args.get('mes', '').strip()
        data_inventario = request.args.get('data_inventario', '').strip()
        
        estoque_bruto_lista = []
        
        def limpar_codigo_operacional(c_texto):
            if not c_texto: return ""
            texto_str = str(c_texto).upper().strip()
            texto_str = texto_str.replace('[', '').replace(']', '').replace('"', '')
            return re.sub(r'[^A-Z0-9]', '', texto_str)
        
        # 1️⃣ LEITURA DO ARQUIVO DA CORAX TRATADA CONTRA QUEDAS
        try:
            arquivo_estoque = buscar_ultimo_estoque_downloads()
            if arquivo_estoque:
                with open(arquivo_estoque, mode='r', encoding='utf-8', errors='ignore') as f:
                    linhas_arquivo = f.readlines()
                idx_codigo, idx_saldo = 1, 6
                for linha_texto in linhas_arquivo:
                    if linha_texto.strip().startswith(',,,,') or len(linha_texto.strip()) < 10: continue
                    colunas = [c.replace('"', '').strip() for c in linha_texto.split(',')]
                    if len(colunas) <= max(idx_codigo, idx_saldo): continue
                    cod_cru = colunas[idx_codigo]
                    if not cod_cru or cod_cru.upper() in ['NAN', '', 'NONE', 'NULL', 'CÓDIGO DO PRODUTO', 'CODIGO DO PRODUTO']: continue
                    chave_excel_limpa = limpar_codigo_operacional(cod_cru)
                    try:
                        raw_saldo = colunas[idx_saldo].replace(' ', '').strip()
                        parte_inteira = raw_saldo.split(',')[0].replace('.', '')
                        parte_inteira = re.sub(r'[^0-9-]', '', parte_inteira)
                        saldo_num = int(parte_inteira) if parte_inteira else 0
                    except Exception: saldo_num = 0
                    estoque_bruto_lista.append({"chave_limpa": chave_excel_limpa, "saldo": saldo_num})
        except Exception as e_file:
            print(f"⚠️ [AVISO CORAX IGNORADO PARA NÃO TRAVAR O AUDITOR]: {str(e_file)}")

        # 2️⃣ CONSULTA DO HISTÓRICO DE VENDAS TRATADA
        vendas_por_item = {}
        descricoes_por_item = {}
        total_geral_vendas = 0
        
        # Declaramos a conexão fora para garantir a leitura segura no bloco 3
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT TOP 1 * FROM faturamento_itens" if database_adapter.is_sqlserver() else "SELECT * FROM faturamento_itens LIMIT 1")
            colunas_existentes = [desc[0].lower().strip() for desc in cursor.description]
            col_codigo = 'codigo_item' if 'codigo_item' in colunas_existentes else 'codigo'
            col_desc = 'descricao' if 'descricao' in colunas_existentes else 'produto'
            col_qtd = 'qtd_total' if 'qtd_total' in colunas_existentes else ('quantidade' if 'quantidade' in colunas_existentes else 'qtd')
            col_data = 'data_emissao' if 'data_emissao' in colunas_existentes else ('data' if 'data' in colunas_existentes else 'data_movimento')
            
            if col_desc not in colunas_existentes:
                for c in colunas_existentes:
                    if 'desc' in c or 'prod' in c or 'nome' in c: col_desc = c; break
            if col_qtd not in colunas_existentes:
                for c in colunas_existentes:
                    if 'qtd' in c or 'quant' in c or 'total' in c: col_qtd = c; break

            query_sql = f"SELECT {col_codigo}, {col_desc}, {col_qtd}"
            if col_data in colunas_existentes: query_sql += f", {col_data}"
            query_sql += f" FROM faturamento_itens"
            
            cursor.execute(query_sql)
            for linha in cursor.fetchall():
                if not linha[0]: continue
                cod_limpo_banco = limpar_codigo_operacional(linha[0])
                if not cod_limpo_banco or len(cod_limpo_banco) < 3: continue
                if mes_escolhido and col_data in colunas_existentes and len(linha) > 3 and linha[3]:
                    if mes_escolhido not in str(linha[3]): continue
                desc = str(linha[1]).strip().upper() if linha[1] else ""
                if desc == "" or desc.isdigit() or "SEM DESCRIÇÃO" in desc: continue
                raw_qtd = str(linha[2]).strip() if linha[2] else "0"
                num_limpo = "".join([char for char in raw_qtd if char.isdigit()])
                qtd = int(num_limpo) if (num_limpo != "" and len(num_limpo) < 5) else 0
                if qtd > 0:
                    vendas_por_item[cod_limpo_banco] = vendas_por_item.get(cod_limpo_banco, 0) + qtd
                    total_geral_vendas += qtd
                    descricoes_por_item[cod_limpo_banco] = desc
        except Exception as e_db:
            print(f"⚠️ [AVISO BANCO FATURAMENTO]: {str(e_db)}")

        # 3️⃣ BUSCA DE INVENTÁRIO TOTAL SEM TRAVA DE DATA (Conexão fechada apenas após o uso)
        lancamentos_salvos = {}
        try:
            cursor.execute("""
                SELECT codigo_item, quantidade_real, lote_peca, responsavel, descricao_item 
                FROM historico_inventario_ciclico 
                ORDER BY id DESC
            """)
            for c_item, qtd_r, lote, resp, desc_i in cursor.fetchall():
                cod_chave_limpa = limpar_codigo_operacional(c_item)
                if cod_chave_limpa not in lancamentos_salvos:
                    lancamentos_salvos[cod_chave_limpa] = []
                lancamentos_salvos[cod_chave_limpa].append({
                    "quantidade_real": qtd_r,
                    "lote": lote if lote else "GERAL",
                    "responsavel": resp
                })
                if cod_chave_limpa not in descricoes_por_item and desc_i:
                    descricoes_por_item[cod_chave_limpa] = str(desc_i).strip().upper()
        except Exception as e_hist:
            print(f"⚠️ Erro histórico cíclico: {e_hist}")

        #if 'conn' in locals() and conn: conn.close()

        if total_geral_vendas == 0: total_geral_vendas = 1

        # 4️⃣ GARANTIA CIRÚRGICA: INJEÇÃO DOS ITENS DO INVENTÁRIO QUE NÃO TÊM VENDAS
        for cod_salvo in lancamentos_salvos.keys():
            if cod_salvo not in vendas_por_item:
                vendas_por_item[cod_salvo] = 0

        lista_dados_final = []
        acumulado_percentual = 0.0

        itens_ordenados = sorted(vendas_por_item.items(), key=lambda x: x[1], reverse=False)
        for cod_item, qtd_vendas in reversed(itens_ordenados):
            desc_item = descricoes_por_item.get(cod_item, "PRODUTO SEM DESCRIÇÃO CADASTRADA")
            
            saldo_encontrado = 0
            for est in estoque_bruto_lista:
                if (cod_item in est["chave_limpa"]) or (est["chave_limpa"] in cod_item):
                    saldo_encontrado = est["saldo"]
                    break
            
            historicos = lancamentos_salvos.get(cod_item, [])
            if historicos:
                saldo_encontrado = historicos[0]["quantidade_real"]

            percent_individual = (qtd_vendas / total_geral_vendas) * 100
            acumulado_percentual += percent_individual
            
            lista_dados_final.append({
                "codigo_item": cod_item,
                "descricao": desc_item,
                "vendas": qtd_vendas,
                "saldo_sistema": saldo_encontrado,
                "participacao": round(percent_individual, 2),
                "acumulado": round(acumulado_percentual, 2),
                "lancamentos_historicos": historicos
            })
        if 'conn' in locals() and conn: conn.close()
        return jsonify(lista_dados_final), 200
            
        return jsonify(lista_dados_final), 200
        
    except Exception as e:
        print(f"❌ [ERRO INTERN PREVENIDO]: {str(e)}")
        if 'conn' in locals() and conn: conn.close()
        return jsonify([]), 200
    
@app.route('/api/logistica/resumo_curvas_inventario', methods=['GET'])
def api_resumo_curvas_inventario():
    """MÓDULO ADRIANO - CARDS DE RESUMO: Calcula dinamicamente quantos itens 
    de cada curva (A, B, C) já foram inventariados no pátio."""
    import sqlite3
    from flask import jsonify
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1️⃣ Pegamos todos os itens que já foram inventariados
        cursor.execute("SELECT DISTINCT codigo_item FROM historico_inventario_ciclico")
        itens_inventariados = {str(row[0]).strip().upper() for row in cursor.fetchall()}
        
        # 2️⃣ Buscamos a classificação de vendas para definir as curvas
        # Usamos uma cópia simplificada da sua lógica de faturamento para ser ultra veloz
        if database_adapter.is_sqlserver():
            cursor.execute("""
                SELECT codigo_item,
                       SUM(COALESCE(TRY_CONVERT(float, REPLACE(CAST(qtde AS nvarchar(50)), ',', '.')), 0))
                FROM faturamento_itens
                GROUP BY codigo_item
                ORDER BY SUM(COALESCE(TRY_CONVERT(float, REPLACE(CAST(qtde AS nvarchar(50)), ',', '.')), 0)) DESC
            """)
        else:
            cursor.execute("""
                SELECT codigo_item, SUM(qtde) 
                FROM faturamento_itens 
                GROUP BY codigo_item 
                ORDER BY SUM(qtde) DESC
            """)
        vendas = cursor.fetchall()
        conn.close()
        
        total_vendas = sum(row[1] for row in vendas) if vendas else 1
        if total_vendas == 0: total_vendas = 1
        
        # 3️⃣ Contabilizamos os cards com base no que REALMENTE foi inventariado
        cards = {"A": 0, "B": 0, "C": 0}
        acumulado = 0.0
        
        for cod, qtd in vendas:
            cod_limpo = str(cod).strip().upper()
            percent = (qtd / total_vendas) * 100
            acumulado += percent
            
            # Define a curva baseada na sua regra de Pareto
            if acumulado <= 80.0:
                curva = "A"
            elif acumulado <= 95.0:
                curva = "B"
            else:
                curva = "C"
                
            # Se esse item da curva foi inventariado pelo operador, soma no card
            if cod_limpo in itens_inventariados:
                cards[curva] += 1
                itens_inventariados.remove(cod_limpo) # Evita duplicidade
                
        # Itens novos (como o Trava-Quedas) que não têm histórico de faturamento entram na Curva C por padrão
        cards["C"] += len(itens_inventariados)
        
        return jsonify(cards), 200
        
    except Exception as e:
        print(f"⚠️ [ERRO CARDS RESUMO]: {str(e)}")
        if conn: conn.close()
        return jsonify({"A": 0, "B": 0, "C": 0}), 200
    
@app.route('/espiao')
def abrir_espiao():
    return render_template('espiao.html')

# =====================================================================
# 🔄 MÓDULO DE INVENTÁRIO CÍCLICO COM SUPORTE A MÚLTIPLOS LOTES
# =====================================================================

def inicializar_tabela_inventario_ciclico():
    """Garante a existência da tabela com suporte a lote no SQLite."""
    import sqlite3
    if database_adapter.is_sqlserver():
        print("[INVENTARIO] SQL Server ativo: tabela gerenciada pelo schema principal.")
        return
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_inventario_ciclico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_contagem TEXT NOT NULL,
            responsavel TEXT NOT NULL,
            codigo_item TEXT NOT NULL,
            descricao_item TEXT,
            quantidade_real INTEGER NOT NULL,
            lote_peca TEXT NOT NULL, -- 🎯 Coluna do Lote adicionada
            saldo_anterior INTEGER NOT NULL,
            data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 🛡️ MIGRAÇÃO DE SEGURANÇA: adiciona a coluna em bancos antigos que já existiam sem ela
    try:
        cursor.execute("ALTER TABLE historico_inventario_ciclico ADD COLUMN lote_peca TEXT")
    except sqlite3.OperationalError:
        pass  # Se a coluna já existir, ignora o erro com segurança

    conn.commit()
    conn.close()

try:
    inicializar_tabela_inventario_ciclico()
except Exception as e_db:
    print(f"⚠️ [AVISO BANCO DE DADOS]: {str(e_db)}")


@app.route('/lancar_contagem')
def abrir_lancar_contagem():
    return render_template('lancar_contagem.html')


@app.route('/api/logistica/salvar_contagem', methods=['POST'])
@login_requerido()
def api_salvar_contagem_estoque():
    """Recebe o payload com lotes fracionados e salva linha por linha no SQLite."""
    try:
        import sqlite3
        from flask import request, jsonify
        
        payload = request.get_json()
        if not payload:
            return jsonify({"status": "erro", "mensagem": "Payload vazio."}), 400
            
        data_contagem = payload.get('data')
        responsavel = payload.get('responsavel', '').strip().upper()
        movimentacoes = payload.get('movimentacoes', [])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        linhas_inseridas = 0
        for item in movimentacoes:
            codigo = str(item.get('codigo')).strip()
            descricao = str(item.get('descricao', '')).strip().upper()
            qtd_real = int(item.get('quantidade_real', 0))
            lote = str(item.get('lote', 'SEM LOTE')).strip().upper()
            saldo_ant = int(item.get('saldo_anterior', 0))
            
            # Executa a inserção amarrando o lote individual de cada registro
            cursor.execute("""
                INSERT INTO historico_inventario_ciclico 
                (data_contagem, responsavel, codigo_item, descricao_item, quantidade_real, lote_peca, saldo_anterior)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (data_contagem, responsavel, codigo, descricao, qtd_real, lote, saldo_ant))
            linhas_inseridas += 1
            
        conn.commit()
        conn.close()
        
        return jsonify({"status": "sucesso", "itens_gravados": linhas_inseridas}), 200
        
    except Exception as e:
        print(f"❌ [ERRO INVENTÁRIO CÍCLICO]: {str(e)}")
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    
@app.route('/logistica/espiao')
def tela_espiao_logistica():
    """Garante que o Flask abra o arquivo HTML da pasta templates"""
    return render_template('espiao_base.html')    
    
@app.route('/api/logistica/espiao_base_bruta', methods=['GET'])
def api_espiao_base():
    import sqlite3
    from flask import jsonify
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, data_contagem, responsavel, codigo_item, 
                   descricao_item, quantidade_real, lote_peca, saldo_anterior 
            FROM historico_inventario_ciclico
            ORDER BY id DESC
        """)
        linhas = cursor.fetchall()
        conn.close()
        
        resultado_bruto = []
        for l in linhas:
            resultado_bruto.append({
                "id": l[0],
                "data_contagem": str(l[1]).strip(),
                "responsavel": str(l[2]).strip().upper(),
                "codigo_item": str(l[3]).strip(),
                "descricao": str(l[4]).strip().upper(),
                "quantidade_real": l[5],
                "lote_peca": l[6] if l[6] else "GERAL",
                "saldo_anterior": l[7] if l[7] is not None else "-"
            })
            
        return jsonify(resultado_bruto), 200
        
    except Exception as e:
        print(f"❌ [ERRO REAL NO ESPIÃO]: {str(e)}")   # 👈 linha nova
        if conn: conn.close()
        return jsonify([]), 200


# ============================================================
# ROTEIRIZADOR LOGÍSTICO (CEP, mesorregião, rotas, veículos)
# ============================================================
from modulo_roteirizador import registrar_rotas_roteirizador

registrar_rotas_roteirizador(app, {
    'get_db': get_db_connection,
    'login_requerido': login_requerido,
    'limpar_nf': _limpar_numero_nf,
    'carregar_expedicao': carregar_dataframe_expedicao,
    'obter_planilha_expedicao': obter_planilha_expedicao_conciliacao,
})


if __name__ == '__main__':
    import time
    import argparse

    parser = argparse.ArgumentParser(description='Sistema Logístico Integrado')
    parser.add_argument('--servidor', action='store_true', help='Apenas servidor HTTP na rede (sem janela desktop)')
    parser.add_argument('--porta', type=int, default=5000, help='Porta HTTP (padrão: 5000)')
    args = parser.parse_args()

    porta = args.porta
    ip_rede = obter_ip_local()

    t = threading.Thread(target=lambda: rodar_flask(porta), daemon=True)
    t.start()
    time.sleep(1.2)

    print('\n' + '=' * 56)
    print('SISTEMA LOGÍSTICO INTEGRADO — SERVIDOR ATIVO')
    print(f'  Máquina local:  http://127.0.0.1:{porta}/')
    print(f'  Rede (LAN):     http://{ip_rede}:{porta}/')
    print('  Outros PCs na rede devem usar o endereço LAN acima.')
    print('  Upload manual:  /api/importar_faturamento_manual')
    print('                  /api/importar_expedicao_manual')
    print('=' * 56 + '\n')

    if args.servidor:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print('Servidor encerrado.')
    else:
        url_ignicao = f'http://127.0.0.1:{porta}/?nocache={int(time.time())}'
        webview.create_window('Sistema Operacional Logístico', url_ignicao, width=1360, height=860)
        webview.start()
