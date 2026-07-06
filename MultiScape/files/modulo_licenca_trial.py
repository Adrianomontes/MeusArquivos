# -*- coding: utf-8 -*-
"""Licença trial de 30 dias — arquivo trial.lic com assinatura HMAC (Multi Escape ERP)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

LICENCA_ARQUIVO = 'trial.lic'
DIAS_PADRAO = 30


def _base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _carregar_chave() -> bytes:
    candidatos = [os.environ.get('MULTISCAPE_TRIAL_SECRET', '').strip()]
    base = _base_dir()
    for nome in ('multiscape_trial_secret.key', os.path.join('scripts', 'multiscape_trial_secret.key')):
        caminho = os.path.join(base, nome)
        if os.path.isfile(caminho):
            with open(caminho, encoding='utf-8') as f:
                candidatos.append(f.read().strip())
    for valor in candidatos:
        if valor:
            return valor.encode('utf-8')
    return b'multiscape-trial-dev-altere-esta-chave-em-producao'


def _assinatura(payload: dict[str, Any], chave: bytes) -> str:
    base = '|'.join([
        str(payload.get('email', '')).strip().lower(),
        str(payload.get('empresa', '')).strip(),
        str(payload.get('emitido_em', '')),
        str(payload.get('expira_em', '')),
        str(payload.get('dias', '')),
        'multiscape',
    ])
    return hmac.new(chave, base.encode('utf-8'), hashlib.sha256).hexdigest()


def gerar_licenca(email: str, empresa: str = '', dias: int = DIAS_PADRAO) -> dict[str, Any]:
    emitido = datetime.now().date()
    expira = emitido + timedelta(days=max(1, int(dias)))
    payload = {
        'produto': 'Multi Escape ERP',
        'email': email.strip().lower(),
        'empresa': empresa.strip(),
        'emitido_em': emitido.isoformat(),
        'expira_em': expira.isoformat(),
        'dias': int(dias),
        'edicao': 'trial',
    }
    payload['assinatura'] = _assinatura(payload, _carregar_chave())
    return payload


def salvar_licenca(caminho: str, payload: dict[str, Any]) -> None:
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _validar(dados: dict[str, Any]) -> tuple[bool, str, int]:
    if not dados:
        return False, 'Arquivo de licença vazio.', 0
    esperada = dados.get('assinatura', '')
    copia = {k: v for k, v in dados.items() if k != 'assinatura'}
    if not hmac.compare_digest(_assinatura(copia, _carregar_chave()), str(esperada)):
        return False, 'Licença trial inválida ou adulterada.', 0
    try:
        expira = datetime.fromisoformat(str(dados['expira_em'])).date()
    except (KeyError, ValueError):
        return False, 'Data de expiração inválida na licença.', 0
    restantes = (expira - datetime.now().date()).days
    if restantes < 0:
        return False, f'Período de avaliação encerrado em {expira.strftime("%d/%m/%Y")}.', 0
    return True, 'Licença trial válida.', restantes


def edicao_trial_ativa() -> bool:
    if os.environ.get('EDICAO_TRIAL', '').strip().lower() in ('1', 'true', 'yes', 'sim'):
        return True
    if getattr(sys, 'frozen', False):
        nome = os.path.basename(sys.executable).lower()
        if 'trial' in nome:
            return True
    return os.path.isfile(os.path.join(_base_dir(), LICENCA_ARQUIVO))


def verificar_trial_ou_sair() -> None:
    """Bloqueia o app se edição trial estiver ativa e licença inválida/expirada."""
    if not edicao_trial_ativa():
        return

    import tkinter as tk
    from tkinter import messagebox

    caminho = os.path.join(_base_dir(), LICENCA_ARQUIVO)
    dados: dict[str, Any] = {}
    if os.path.isfile(caminho):
        try:
            with open(caminho, encoding='utf-8') as f:
                dados = json.load(f)
        except (OSError, json.JSONDecodeError):
            dados = {}

    ok, msg, restantes = _validar(dados)
    if ok:
        return

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        'Multi Escape ERP — Trial',
        msg + '\n\nContato: adrianomontes55@gmail.com\nAnimo Serviços Administrativos',
    )
    root.destroy()
    sys.exit(1)
