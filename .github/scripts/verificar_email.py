#!/usr/bin/env python3
"""Valida se o autor do último commit está na lista de e-mails autorizados."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = ROOT / ".github" / "access-control.json"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _normalizar(email: str) -> str:
    return email.strip().lower()


def _autorizado(email: str, permitidos: list[str]) -> bool:
    email_n = _normalizar(email)
    if email_n in {_normalizar(e) for e in permitidos}:
        return True
    # Commits via interface GitHub usam noreply
    if re.match(r"^\d+\+[^@]+@users\.noreply\.github\.com$", email_n):
        usuario = email_n.split("+", 1)[1].split("@", 1)[0]
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
        usuarios = {_normalizar(u) for u in cfg.get("usuarios_github_autorizados", [])}
        return _normalizar(usuario) in usuarios
    return False


def main() -> int:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    permitidos = cfg.get("emails_autorizados", [])
    autor_email = _git("log", "-1", "--format=%ae")
    autor_nome = _git("log", "-1", "--format=%an")

    if _autorizado(autor_email, permitidos):
        print(f"OK: {autor_nome} <{autor_email}> autorizado.")
        return 0

    print(
        f"::error::E-mail não autorizado: {autor_nome} <{autor_email}>. "
        f"Adicione em .github/access-control.json ou use conta GitHub vinculada ao e-mail permitido.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
