#!/usr/bin/env python3
"""Monta ZIP de envio trial: exe + trial.lic + banco demo + instruções."""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)


def main() -> int:
    parser = argparse.ArgumentParser(description='Montar pacote ZIP trial para cliente')
    parser.add_argument('--email', required=True)
    parser.add_argument('--empresa', default='')
    parser.add_argument('--dias', type=int, default=15)
    parser.add_argument('--exe', default=os.path.join(BASE, 'dist', 'SistemaLogisticoTrial.exe'))
    args = parser.parse_args()

    if not os.path.isfile(args.exe):
        print(f'[ERRO] Executável não encontrado: {args.exe}')
        print('Execute build_executavel_trial.bat primeiro.')
        return 1

    slug = args.email.replace('@', '_at_').replace('.', '_')
    pasta = os.path.join(BASE, 'trial_distribuicao', 'envios', slug)
    os.makedirs(pasta, exist_ok=True)

    # Licença
    subprocess.check_call([
        sys.executable,
        os.path.join(BASE, 'scripts', 'gerar_licenca_trial.py'),
        '--email', args.email,
        '--empresa', args.empresa,
        '--dias', str(args.dias),
        '--saida', os.path.join(pasta, 'trial.lic'),
    ])

    # Banco trial
    if not os.path.isfile(os.path.join(BASE, 'sistema_trial.db')):
        subprocess.check_call([sys.executable, os.path.join(BASE, 'scripts', 'criar_banco_trial.py')])
    shutil.copy2(os.path.join(BASE, 'sistema_trial.db'), os.path.join(pasta, 'sistema_trial.db'))

    # Exe e auxiliares
    shutil.copy2(args.exe, os.path.join(pasta, 'SistemaLogisticoTrial.exe'))
    for nome in ('MODAIS.csv', 'liberar_porta_firewall.bat'):
        origem = os.path.join(BASE, nome)
        if os.path.isfile(origem):
            shutil.copy2(origem, os.path.join(pasta, nome))
    db_cep = os.path.join(BASE, 'database', 'cep_mesorregiao_brasil.db')
    if os.path.isfile(db_cep):
        os.makedirs(os.path.join(pasta, 'database'), exist_ok=True)
        shutil.copy2(db_cep, os.path.join(pasta, 'database', 'cep_mesorregiao_brasil.db'))

    readme = os.path.join(BASE, 'trial_distribuicao', 'LEIA-ME_CLIENTE.txt')
    if os.path.isfile(readme):
        shutil.copy2(readme, os.path.join(pasta, 'LEIA-ME_CLIENTE.txt'))

    zip_path = os.path.join(BASE, 'trial_distribuicao', 'envios', f'trial_{slug}.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(pasta):
            for arq in files:
                if arq.endswith('.zip'):
                    continue
                caminho = os.path.join(root, arq)
                zf.write(caminho, os.path.relpath(caminho, pasta))

    print(f'\nPacote pronto: {zip_path}')
    print('Envie SOMENTE este ZIP ao cliente (não envie o código-fonte).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
