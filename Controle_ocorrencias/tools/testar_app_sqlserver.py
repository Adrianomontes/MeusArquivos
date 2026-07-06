"""Smoke test do app usando SQL Server.

Nao sobe navegador nem servidor. Apenas importa o app, testa conexao, login e
contagens basicas para validar a fase de migracao.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


os.environ.setdefault("DB_BACKEND", "sqlserver")
os.environ.setdefault("SQLSERVER_HOST", "localhost")
os.environ.setdefault("SQLSERVER_DATABASE", "SistemaLogistico")
os.environ.setdefault("SQLSERVER_TRUSTED_CONNECTION", "yes")
os.environ.setdefault("SQLSERVER_TRUST_CERT", "yes")

import app  # noqa: E402


def main() -> int:
    print("Backend:", app.database_adapter.describe_backend())

    conn = app.get_db_connection()
    try:
        faturamento = conn.execute("SELECT COUNT(*) AS total FROM faturamento").fetchone()["total"]
        usuarios = conn.execute("SELECT COUNT(*) AS total FROM usuarios_sistema").fetchone()["total"]
        print("faturamento:", faturamento)
        print("usuarios_sistema:", usuarios)
    finally:
        conn.close()

    client = app.app.test_client()
    resp = client.post("/login", json={"login": "admin", "senha": "admin123"})
    print("login_admin:", resp.status_code, resp.get_json())
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
