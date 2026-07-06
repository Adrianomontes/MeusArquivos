"""
Controle de edição TRIAL — licença por arquivo trial.lic com expiração e limites.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

LICENCA_ARQUIVO = 'trial.lic'
DB_TRIAL = 'sistema_trial.db'
DIAS_PADRAO = 15

ROTAS_BLOQUEADAS_TRIAL = (
    '/exportar',
    '/exportar_coletas',
    '/exportar_transportadoras',
    '/exportar_canhotos',
    '/exportar_base_faturamento',
    '/exportar_base_expedicao',
    '/exportar_faturamento_filtrado',
    '/gerenciar_usuarios',
)

ROTAS_LIBERADAS_SEM_LICENCA = (
    '/trial-expirado',
    '/trial-invalido',
    '/static/',
)


@dataclass
class TrialConfig:
    ativo: bool
    valido: bool
    expirado: bool
    db_path: str
    licenca: dict[str, Any] | None
    dias_restantes: int
    mensagem: str


_state: TrialConfig | None = None


def _carregar_chave_secreta() -> bytes:
    candidatos = [os.environ.get('TRIAL_SECRET_KEY', '').strip()]
    base = os.path.dirname(os.path.abspath(__file__))
    for nome in ('trial_secret.key', os.path.join('scripts', 'trial_secret.key')):
        caminho = os.path.join(base, nome)
        if os.path.isfile(caminho):
            with open(caminho, encoding='utf-8') as f:
                candidatos.append(f.read().strip())
    for valor in candidatos:
        if valor:
            return valor.encode('utf-8')
    return b'animo-trial-dev-altere-esta-chave-em-producao'


def _assinatura(payload: dict[str, Any], chave: bytes) -> str:
    base = '|'.join([
        str(payload.get('email', '')).strip().lower(),
        str(payload.get('empresa', '')).strip(),
        str(payload.get('emitido_em', '')),
        str(payload.get('expira_em', '')),
        str(payload.get('dias', '')),
    ])
    return hmac.new(chave, base.encode('utf-8'), hashlib.sha256).hexdigest()


def gerar_licenca(email: str, empresa: str = '', dias: int = DIAS_PADRAO) -> dict[str, Any]:
    emitido = datetime.now().date()
    expira = emitido + timedelta(days=max(1, int(dias)))
    payload = {
        'email': email.strip().lower(),
        'empresa': empresa.strip(),
        'emitido_em': emitido.isoformat(),
        'expira_em': expira.isoformat(),
        'dias': int(dias),
        'edicao': 'trial',
    }
    payload['assinatura'] = _assinatura(payload, _carregar_chave_secreta())
    return payload


def salvar_licenca(caminho: str, payload: dict[str, Any]) -> None:
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _validar_licenca(dados: dict[str, Any]) -> tuple[bool, str, int]:
    if not dados:
        return False, 'Arquivo de licença vazio.', 0
    esperada = dados.get('assinatura', '')
    copia = {k: v for k, v in dados.items() if k != 'assinatura'}
    if not hmac.compare_digest(_assinatura(copia, _carregar_chave_secreta()), str(esperada)):
        return False, 'Licença trial inválida ou adulterada.', 0
    try:
        expira = datetime.fromisoformat(str(dados['expira_em'])).date()
    except (KeyError, ValueError):
        return False, 'Data de expiração inválida na licença.', 0
    hoje = datetime.now().date()
    restantes = (expira - hoje).days
    if restantes < 0:
        return False, f'Licença trial expirada em {expira.strftime("%d/%m/%Y")}.', 0
    return True, 'Licença trial válida.', restantes


def _exe_eh_trial() -> bool:
    if os.environ.get('EDICAO_TRIAL', '').strip().lower() in ('1', 'true', 'yes', 'sim'):
        return True
    if getattr(sys, 'frozen', False):
        nome = os.path.basename(sys.executable).lower()
        if 'trial' in nome:
            return True
    return False


def configurar_trial(base_dir: str) -> TrialConfig:
    global _state
    if _state is not None:
        return _state

    lic_path = os.path.join(base_dir, LICENCA_ARQUIVO)
    db_trial = os.path.join(base_dir, DB_TRIAL)
    db_full = os.path.join(base_dir, 'sistema_operacional.db')
    setup = os.environ.get('TRIAL_DB_SETUP') == '1'

    exige_trial = _exe_eh_trial() or os.path.isfile(lic_path)
    licenca = None
    valido = False
    expirado = False
    mensagem = ''
    dias_restantes = 0

    if os.path.isfile(lic_path):
        try:
            with open(lic_path, encoding='utf-8') as f:
                licenca = json.load(f)
            valido, mensagem, dias_restantes = _validar_licenca(licenca)
            expirado = not valido and 'expirada' in mensagem.lower()
        except (OSError, json.JSONDecodeError) as exc:
            mensagem = f'Erro ao ler licença trial: {exc}'
    elif exige_trial and not setup:
        mensagem = (
            'Executável TRIAL sem arquivo trial.lic. '
            'Solicite a licença à Animo Serviços Administrativos.'
        )
    else:
        mensagem = 'Edição completa (sem trial).'

    ativo = (exige_trial or (valido and os.path.isfile(lic_path))) and not setup

    if setup or exige_trial or ativo:
        db_path = db_trial
    else:
        db_path = db_full

    _state = TrialConfig(
        ativo=ativo,
        valido=valido if not setup else True,
        expirado=expirado,
        db_path=db_path,
        licenca=licenca,
        dias_restantes=dias_restantes,
        mensagem=mensagem,
    )
    return _state


def trial_ativo() -> bool:
    return bool(_state and _state.ativo)


def info_trial() -> dict[str, Any]:
    if not _state or not _state.ativo:
        return {'ativo': False}
    lic = _state.licenca or {}
    return {
        'ativo': True,
        'valido': _state.valido,
        'expirado': _state.expirado,
        'dias_restantes': _state.dias_restantes,
        'email': lic.get('email', ''),
        'empresa': lic.get('empresa', ''),
        'expira_em': lic.get('expira_em', ''),
        'mensagem': _state.mensagem,
    }


def verificar_rota_trial(path: str):
    if not trial_ativo():
        return None

    cfg = _state
    assert cfg is not None

    for prefixo in ROTAS_LIBERADAS_SEM_LICENCA:
        if path.startswith(prefixo):
            return None

    if not cfg.valido:
        if path in ('/trial-expirado', '/trial-invalido'):
            return None
        from flask import redirect
        alvo = '/trial-expirado' if cfg.expirado else '/trial-invalido'
        if path != alvo:
            return redirect(alvo)

    for rota in ROTAS_BLOQUEADAS_TRIAL:
        if path == rota or path.startswith(rota + '/'):
            html = (
                "<body style='background:#0f172a;color:#f59e0b;font-family:Segoe UI,sans-serif;"
                "padding:48px;text-align:center;'>"
                "<h2>Recurso indisponível na versão TRIAL</h2>"
                "<p>Exportações completas e gestão de usuários são exclusivas da edição licenciada.</p>"
                "<p>Contato: adrianomontes55@gmail.com — Animo Serviços Administrativos</p>"
                "<a href='/portal_operacional' style='color:#38bdf8;'>Voltar ao portal</a></body>"
            )
            return html, 403

    return None


def validar_limite_importacao_trial(qtd_linhas: int, limite: int = 80) -> str | None:
    if not trial_ativo():
        return None
    if qtd_linhas > limite:
        return (
            f'Versão TRIAL: importação limitada a {limite} linhas por arquivo. '
            'Solicite a edição completa à Animo Serviços Administrativos.'
        )
    return None


PAGINA_TRIAL_EXPIRADO = """
<!DOCTYPE html><html lang="pt-br"><head><meta charset="UTF-8"><title>Trial expirado</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0f172a;color:#f8fafc;font-family:Segoe UI,sans-serif;padding:24px;text-align:center;}
.box{max-width:480px;background:#1e293b;border:1px solid #334155;border-radius:12px;padding:32px;}
h1{color:#f59e0b;font-size:1.4rem;}p{color:#94a3b8;line-height:1.6;}a{color:#38bdf8;}</style></head>
<body><div class="box"><h1>Período de avaliação encerrado</h1>
<p>Sua licença trial expirou. Para continuar, contate a <strong>Animo Serviços Administrativos</strong>.</p>
<p><strong>Contato:</strong> Adriano Montes (Animo)<br>
<a href="mailto:adrianomontes55@gmail.com">adrianomontes55@gmail.com</a></p>
</div></body></html>
"""

PAGINA_TRIAL_INVALIDO = """
<!DOCTYPE html><html lang="pt-br"><head><meta charset="UTF-8"><title>Licença trial</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0f172a;color:#f8fafc;font-family:Segoe UI,sans-serif;padding:24px;text-align:center;}
.box{max-width:480px;background:#1e293b;border:1px solid #334155;border-radius:12px;padding:32px;}
h1{color:#ef4444;font-size:1.4rem;}p{color:#94a3b8;line-height:1.6;}a{color:#38bdf8;}</style></head>
<body><div class="box"><h1>Licença trial necessária</h1>
<p>{{ mensagem }}</p>
<p>Contato: <a href="mailto:adrianomontes55@gmail.com">adrianomontes55@gmail.com</a></p>
</div></body></html>
"""
