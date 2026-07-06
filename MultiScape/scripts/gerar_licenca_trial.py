#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera trial.lic para envio ao cliente (uso interno)."""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from modulo_licenca_trial import DIAS_PADRAO, gerar_licenca, salvar_licenca


def main():
    parser = argparse.ArgumentParser(description='Gerar trial.lic — Multi Escape ERP')
    parser.add_argument('--email', required=True, help='E-mail corporativo do cliente')
    parser.add_argument('--empresa', default='', help='Nome da oficina')
    parser.add_argument('--dias', type=int, default=DIAS_PADRAO, help='Dias de trial (padrão 30)')
    parser.add_argument('--saida', default='trial.lic', help='Arquivo de saída')
    args = parser.parse_args()

    payload = gerar_licenca(args.email, args.empresa, args.dias)
    saida = args.saida if os.path.isabs(args.saida) else os.path.join(os.getcwd(), args.saida)
    salvar_licenca(saida, payload)
    print(f'Licença gerada: {saida}')
    print(f'  Válida até: {payload["expira_em"]} ({payload["dias"]} dias)')


if __name__ == '__main__':
    main()
