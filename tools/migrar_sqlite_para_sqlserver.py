"""Migra dados do SQLite para SQL Server.

Por padrao, roda em modo diagnostico. Para gravar no SQL Server, use --execute.

Exemplo:
  python tools/migrar_sqlite_para_sqlserver.py --execute --truncate
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


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


def sqlserver_connection_string() -> str:
    explicit = os.environ.get("SQLSERVER_CONNECTION_STRING", "").strip()
    if explicit:
        return explicit

    host = os.environ.get("SQLSERVER_HOST", "localhost")
    database = os.environ.get("SQLSERVER_DATABASE", "SistemaLogistico")
    driver = os.environ.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
    trusted = os.environ.get("SQLSERVER_TRUSTED_CONNECTION", "yes").strip().lower()
    trust_cert = os.environ.get("SQLSERVER_TRUST_CERT", "yes")

    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={host}",
        f"DATABASE={database}",
        f"TrustServerCertificate={trust_cert}",
    ]
    if trusted in {"1", "true", "yes", "sim"}:
        parts.append("Trusted_Connection=yes")
    else:
        user = os.environ.get("SQLSERVER_USER", "")
        password = os.environ.get("SQLSERVER_PASSWORD", "")
        if not user:
            raise RuntimeError("Defina SQLSERVER_USER ou use SQLSERVER_TRUSTED_CONNECTION=yes.")
        parts.extend([f"UID={user}", f"PWD={password}"])

    return ";".join(parts) + ";"


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [r[1] for r in rows]


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def has_identity_id(columns: list[str]) -> bool:
    return "id" in columns


def chunks(rows, size: int):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def bracket(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def migrate_table(sqlite_conn, sqlserver_conn, table: str, batch_size: int, truncate: bool) -> int:
    columns = sqlite_columns(sqlite_conn, table)
    if not columns:
        print(f"AVISO: tabela sem colunas ou inexistente no SQLite: {table}")
        return 0

    source_count = sqlite_count(sqlite_conn, table)
    if source_count == 0:
        print(f"{table}: 0 registros")
        return 0

    col_sql = ", ".join(bracket(c) for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    select_sql = f'SELECT {", ".join(chr(34) + c + chr(34) for c in columns)} FROM "{table}"'
    insert_sql = f"INSERT INTO dbo.{bracket(table)} ({col_sql}) VALUES ({placeholders})"

    src_cur = sqlite_conn.cursor()
    dst_cur = sqlserver_conn.cursor()
    dst_cur.fast_executemany = True

    if truncate:
        dst_cur.execute(f"DELETE FROM dbo.{bracket(table)}")

    identity_on = has_identity_id(columns)
    if identity_on:
        dst_cur.execute(f"SET IDENTITY_INSERT dbo.{bracket(table)} ON")

    inserted = 0
    try:
        src_cur.execute(select_sql)
        while True:
            rows = src_cur.fetchmany(batch_size)
            if not rows:
                break
            dst_cur.executemany(insert_sql, [tuple(row) for row in rows])
            inserted += len(rows)
            print(f"{table}: {inserted}/{source_count}")
    finally:
        if identity_on:
            dst_cur.execute(f"SET IDENTITY_INSERT dbo.{bracket(table)} OFF")

    return inserted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migra dados do SQLite para SQL Server.")
    parser.add_argument("--sqlite", default=str(SQLITE_DB), help="Caminho do sistema_operacional.db")
    parser.add_argument("--execute", action="store_true", help="Grava dados no SQL Server.")
    parser.add_argument("--truncate", action="store_true", help="Limpa tabelas de destino antes de inserir.")
    parser.add_argument("--batch-size", type=int, default=500, help="Tamanho do lote de insercao.")
    parser.add_argument("--tables", nargs="*", default=TABLES, help="Lista opcional de tabelas.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"Banco SQLite nao encontrado: {sqlite_path}")
        return 1

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    print("Origem SQLite:", sqlite_path)
    print("Tabelas selecionadas:", len(args.tables))
    for table in args.tables:
        print(f"  {table}: {sqlite_count(sqlite_conn, table)}")

    if not args.execute:
        print("\nModo diagnostico. Use --execute para gravar no SQL Server.")
        sqlite_conn.close()
        return 0

    try:
        import pyodbc
    except ImportError:
        print("pyodbc nao esta instalado. Instale as dependencias antes da migracao.")
        return 1

    sqlserver_conn = pyodbc.connect(sqlserver_connection_string())
    try:
        for table in args.tables:
            migrate_table(sqlite_conn, sqlserver_conn, table, args.batch_size, args.truncate)
        sqlserver_conn.commit()
    except Exception:
        sqlserver_conn.rollback()
        raise
    finally:
        sqlserver_conn.close()
        sqlite_conn.close()

    print("Migracao concluida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
