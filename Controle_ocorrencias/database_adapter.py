"""Camada central de conexao do banco.

Por padrao, o sistema continua usando SQLite. A opcao SQL Server fica preparada
para a migracao gradual, controlada por variaveis de ambiente.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator


_sqlite_path: str | None = None


class DatabaseConfigError(RuntimeError):
    """Erro de configuracao do banco."""


class RowProxy:
    """Linha com acesso por indice, nome de coluna ou atributo."""

    def __init__(self, columns: list[str], row):
        self._columns = columns
        self._row = row
        self._index = {name: pos for pos, name in enumerate(columns)}

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._row[self._index[key]]
        return self._row[key]

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __iter__(self) -> Iterator:
        return iter(self._row)

    def __len__(self) -> int:
        return len(self._row)

    def keys(self) -> list[str]:
        return list(self._columns)

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def as_dict(self) -> dict:
        return {column: self[column] for column in self._columns}


class CursorProxy:
    """Cursor pyodbc com fetch compatível com sqlite3.Row."""

    def __init__(self, cursor):
        self._cursor = cursor

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)

    def execute(self, *args, **kwargs):
        self._cursor.execute(*args, **kwargs)
        return self

    def executemany(self, *args, **kwargs):
        self._cursor.executemany(*args, **kwargs)
        return self

    def _columns(self) -> list[str]:
        if not self._cursor.description:
            return []
        return [col[0] for col in self._cursor.description]

    def _wrap(self, row):
        if row is None:
            return None
        return RowProxy(self._columns(), row)

    def fetchone(self):
        return self._wrap(self._cursor.fetchone())

    def fetchall(self):
        columns = self._columns()
        return [RowProxy(columns, row) for row in self._cursor.fetchall()]

    def fetchmany(self, size=None):
        columns = self._columns()
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        return [RowProxy(columns, row) for row in rows]


class ConnectionProxy:
    """Conexao SQL Server com cursor/fetch semelhantes ao SQLite usado no app."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def cursor(self):
        return CursorProxy(self._conn.cursor())

    def execute(self, *args, **kwargs):
        cursor = self.cursor()
        cursor.execute(*args, **kwargs)
        return cursor


def configure(sqlite_path: str) -> None:
    """Define o caminho do SQLite usado pelo backend padrao."""
    global _sqlite_path
    _sqlite_path = sqlite_path


def backend() -> str:
    """Retorna o backend ativo: sqlite ou sqlserver."""
    return os.environ.get("DB_BACKEND", "sqlite").strip().lower()


def is_sqlserver() -> bool:
    return backend() in {"sqlserver", "mssql", "sql_server"}


def is_sqlite() -> bool:
    return not is_sqlserver()


def _connect_sqlite():
    if not _sqlite_path:
        raise DatabaseConfigError("SQLite nao configurado. Chame database_adapter.configure(DB_FILE).")
    conn = sqlite3.connect(_sqlite_path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _sqlserver_connection_string() -> str:
    explicit = os.environ.get("SQLSERVER_CONNECTION_STRING", "").strip()
    if explicit:
        return explicit

    host = os.environ.get("SQLSERVER_HOST", "localhost").strip()
    database = os.environ.get("SQLSERVER_DATABASE", "SistemaLogistico").strip()
    driver = os.environ.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server").strip()
    trusted = os.environ.get("SQLSERVER_TRUSTED_CONNECTION", "yes").strip().lower()
    trust_cert = os.environ.get("SQLSERVER_TRUST_CERT", "yes").strip()

    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={host}",
        f"DATABASE={database}",
        f"TrustServerCertificate={trust_cert}",
    ]
    if trusted in {"1", "true", "yes", "sim"}:
        parts.append("Trusted_Connection=yes")
    else:
        user = os.environ.get("SQLSERVER_USER", "").strip()
        password = os.environ.get("SQLSERVER_PASSWORD", "")
        if not user:
            raise DatabaseConfigError("Defina SQLSERVER_USER ou use SQLSERVER_TRUSTED_CONNECTION=yes.")
        parts.extend([f"UID={user}", f"PWD={password}"])

    return ";".join(parts) + ";"


def _connect_sqlserver():
    try:
        import pyodbc
    except ImportError as exc:
        raise DatabaseConfigError(
            "Backend SQL Server solicitado, mas pyodbc nao esta instalado."
        ) from exc

    conn = pyodbc.connect(_sqlserver_connection_string())
    return ConnectionProxy(conn)


def get_connection():
    """Abre uma conexao do backend ativo."""
    if is_sqlserver():
        return _connect_sqlserver()
    return _connect_sqlite()


@contextmanager
def transaction():
    """Contexto transacional pequeno para novos modulos."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def describe_backend() -> dict:
    """Retorna dados seguros para diagnostico."""
    if is_sqlserver():
        return {
            "backend": "sqlserver",
            "host": os.environ.get("SQLSERVER_HOST", "localhost"),
            "database": os.environ.get("SQLSERVER_DATABASE", "SistemaLogistico"),
        }
    return {"backend": "sqlite", "path": _sqlite_path}
