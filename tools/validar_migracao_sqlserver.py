"""Valida contagens entre SQLite e SQL Server."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pyodbc


ROOT_DIR = Path(__file__).resolve().parents[1]
SQLITE_DB = ROOT_DIR / "sistema_operacional.db"

TABLES = [
    "usuarios_sistema",
    "logs_auditoria",
    "configuracoes_painel",
    "faturamento",
    "faturamento_itens",
    "entregas_efetuadas",
    "canhotos",
    "canhotos_digitais",
    "devolucoes",
    "coletas",
    "ocorrencias",
    "transportadoras",
    "motivos_ocorrencias",
    "metas_diarias",
    "cep_cache",
    "cabeca_cep_transportadora",
    "faixa_cep_direcionamento",
    "rotas_predefinidas",
    "rotas_predefinidas_criterios",
    "rotas_predefinidas_notas",
    "rotas_saida_dia",
    "de_para_modais",
    "de_para_ean",
    "gestor_emails",
    "historico_inventario_ciclico",
    "templates_monitor",
]


def connection_string() -> str:
    explicit = os.environ.get("SQLSERVER_CONNECTION_STRING", "").strip()
    if explicit:
        return explicit
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.environ.get('SQLSERVER_HOST', 'localhost')};"
        f"DATABASE={os.environ.get('SQLSERVER_DATABASE', 'SistemaLogistico')};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )


def main() -> int:
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sql_conn = pyodbc.connect(connection_string())
    ok = True

    for table in TABLES:
        sqlite_count = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        sql_count = sql_conn.cursor().execute(f"SELECT COUNT(*) FROM dbo.[{table}]").fetchone()[0]
        status = "OK" if sqlite_count == sql_count else "DIVERGENTE"
        if sqlite_count != sql_count:
            ok = False
        print(f"{status} {table}: SQLite={sqlite_count} SQLServer={sql_count}")

    sqlite_conn.close()
    sql_conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
