#!/usr/bin/env python3
"""Gera trial.lic assinado para envio ao cliente (uso interno Animo)."""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from modulo_trial import DIAS_PADRAO, gerar_licenca, salvar_licenca


def main() -> int:
    parser = argparse.ArgumentParser(description='Gerar licença trial assinada')
    parser.add_argument('--email', required=True, help='E-mail do cliente autorizado')
    parser.add_argument('--empresa', default='', help='Nome da empresa')
    parser.add_argument('--dias', type=int, default=DIAS_PADRAO, help='Dias de validade')
    parser.add_argument(
        '--saida',
        default='',
        help='Caminho do arquivo trial.lic (padrão: trial_distribuicao/envios/<email>/trial.lic)',
    )
    args = parser.parse_args()

    payload = gerar_licenca(args.email, args.empresa, args.dias)
    if args.saida:
        destino = args.saida
    else:
        pasta = os.path.join(BASE, 'trial_distribuicao', 'envios', args.email.replace('@', '_at_'))
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(pasta, 'trial.lic')

    salvar_licenca(destino, payload)
    print(f'Licença gerada: {destino}')
    print(f'  E-mail:   {payload["email"]}')
    print(f'  Empresa:  {payload["empresa"] or "(não informada)"}')
    print(f'  Expira:   {payload["expira_em"]} ({payload["dias"]} dias)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
