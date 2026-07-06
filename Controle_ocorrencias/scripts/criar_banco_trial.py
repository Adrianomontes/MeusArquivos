#!/usr/bin/env python3
"""Cria banco SQLite demonstrativo para edição trial (sem dados reais)."""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

os.environ['TRIAL_DB_SETUP'] = '1'
os.chdir(BASE)

import werkzeug.security as ws

DB = os.path.join(BASE, 'sistema_trial.db')
if os.path.isfile(DB):
    os.remove(DB)

# Import após definir ambiente — inicializa schema via app
import app as app_mod  # noqa: E402

app_mod.inicializar_banco()

conn = app_mod.get_db_connection()
cur = conn.cursor()

# Usuário demo trial
senha = ws.generate_password_hash('trial123')
cur.execute(
    "INSERT OR REPLACE INTO usuarios_sistema (login, senha_hash, nome, nivel_hierarquico) VALUES (?, ?, ?, ?)",
    ('trial', senha, 'Usuário Demonstração', 'ADMIN'),
)
cur.execute(
    "INSERT OR REPLACE INTO configuracoes_painel (chave, valor) VALUES ('missao', ?)",
    ('VERSÃO TRIAL — Animo Serviços Administrativos — dados demonstrativos',),
)
cur.execute(
    "INSERT OR REPLACE INTO configuracoes_painel (chave, valor) VALUES ('modo_trial', '1')",
)

conn.commit()
conn.close()

print(f'Banco trial criado: {DB}')
print('Login demo: trial / trial123')
