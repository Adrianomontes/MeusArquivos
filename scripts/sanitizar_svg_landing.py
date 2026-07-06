#!/usr/bin/env python3
"""Corrige SVGs da landing: remove caracteres de controle XML invalidos."""
from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

SUBSTITUICOES = [
    (r'FASE (\d+)\s{1,3}(?!—)', r'FASE \1 — '),
    (r'indicador\s{1,3}controle', 'indicador — controle'),
    (r'saiu do CD\s{1,3}elimina', 'saiu do CD — elimina'),
    (r'Integrado\s{1,3}fluxograma', 'Integrado — fluxograma'),
    (r"pedido.faturamento", 'pedido → faturamento'),
    (r'CEP × IBGE', 'CEP / IBGE'),
]


def limpar_texto(texto: str) -> str:
    # Remove apenas caracteres de controle invalidos em XML 1.0
    texto = ''.join(
        ch for ch in texto
        if ch in '\t\n\r' or ord(ch) >= 32
    )
    if not texto.lstrip().startswith('<?xml'):
        texto = '<?xml version="1.0" encoding="UTF-8"?>\n' + texto

    for pat, rep in SUBSTITUICOES:
        texto = re.sub(pat, rep, texto)

    # Remove lixo antes do texto em titulos (emojis corrompidos)
    def _limpar_titulo(m: re.Match) -> str:
        tag, body = m.group(1), m.group(2)
        body = re.sub(r'^[^A-Za-zÀ-ú(/]+', '', body)
        return tag + body

    texto = re.sub(
        r'(<text[^>]*class="tit"[^>]*>)([^<]*)',
        _limpar_titulo,
        texto,
    )

    return texto


def processar(arquivo: Path) -> None:
    texto = limpar_texto(arquivo.read_text(encoding='utf-8', errors='replace'))
    arquivo.write_text(texto, encoding='utf-8', newline='\n')
    bad = sum(1 for ch in texto if ord(ch) < 32 and ch not in '\t\n\r')
    print(f'OK {arquivo.relative_to(BASE)} (chars invalidos: {bad})')


def main() -> int:
    alvos = [
        BASE / 'docs' / 'assets' / 'fluxograma-operacional-completo.svg',
        BASE / 'docs' / 'assets' / 'fluxo-resumido.svg',
    ]
    for arq in alvos:
        if not arq.exists():
            print('Ausente:', arq)
            continue
        processar(arq)

    for nome in ('fluxograma-operacional-completo.svg', 'fluxo-resumido.svg'):
        src = BASE / 'docs' / 'assets' / nome
        dst = BASE / 'landing-sistema-logistico' / 'assets' / nome
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
            print(f'Copiado -> {dst.relative_to(BASE)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
