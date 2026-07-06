#!/usr/bin/env python3
"""Repara mojibake e XML invalido no fluxograma operacional."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ARQ = BASE / 'docs' / 'assets' / 'fluxograma-operacional-completo.svg'

# Ordem: sequencias longas primeiro
SUBS = [
    ('â€"', '\u2014'),
    ('â†\'', '\u2192'),
    ('ï¿½ï¿½O', 'ÇÃO'),
    ('ï¿½ï¿½o', 'ção'),
    ('ï¿½ï¿½es', 'ções'),
    ('ï¿½ï¿½ES', 'ÇÕES'),
    ('ï¿½ï¿½', 'ç'),
    ('ï¿½', '·'),
    ('log·stico', 'logístico'),
    ('LOG·STICO', 'LOGÍSTICO'),
    ('Log·stico', 'Logístico'),
    ('Gest·o', 'Gestão'),
    ('GEST·O', 'GESTÃO'),
    ('c·digo', 'código'),
    ('Acur·cia', 'Acurácia'),
    ('esp·cie', 'espécie'),
    ('f·sico', 'físico'),
    ('·nica', 'única'),
    ('INTELIG·NCIA', 'INTELIGÊNCIA'),
    ('GEOGR·FICA', 'GEOGRÁFICA'),
    ('mesorregi·es', 'mesorregiões'),
    ('mesorregi·o', 'mesorregião'),
    ('microrregi·o', 'microrregião'),
    ('munic·pio', 'município'),
    ('geogr·fica', 'geográfica'),
    ('pra·as', 'praças'),
    ('sa·da', 'saída'),
    ('n·o', 'não'),
    ('avan·ados', 'avançados'),
    ('Relat·rio', 'Relatório'),
    ('OCORR·NCIAS', 'OCORRÊNCIAS'),
    ('Ocorr·ncias', 'Ocorrências'),
    ('P·tio', 'Pátio'),
    ('hist·rico', 'histórico'),
    ('cobran·a', 'cobrança'),
    ('· VISTA', 'À VISTA'),
    ('Pain·is', 'Painéis'),
    ('efici·ncia', 'eficiência'),
    ('cont·nua', 'contínua'),
    ('CONFI·VEL', 'CONFIÁVEL'),
    ('Um ·nico', 'Um único'),
    ('execut·vel', 'executável'),
    ('confer·ncia', 'conferência'),
    ('CEP · IBGE', 'CEP / IBGE'),
    ('<· ', ''),
    ('<·', ''),
]


def corrigir(texto: str) -> str:
    texto = ''.join(ch for ch in texto if ch in '\t\n\r' or ord(ch) >= 32)
    for antigo, novo in SUBS:
        texto = texto.replace(antigo, novo)
    # Escapa < solto em conteudo de texto (nao tags)
    def _esc(m: re.Match) -> str:
        body = m.group(1).replace('<', '')
        return '>' + body + '<'

    texto = re.sub(r'>([^<]*)<', _esc, texto)
    return texto


def main() -> int:
    raw = ARQ.read_text(encoding='utf-8', errors='replace')
    fix = corrigir(raw)
    ARQ.write_text(fix, encoding='utf-8', newline='\n')
    ET.parse(ARQ)
    print('OK', ARQ.relative_to(BASE))

    for dest in (
        BASE / 'landing-sistema-logistico' / 'assets' / ARQ.name,
        BASE / 'docs' / 'assets' / 'fluxo-resumido.svg',
    ):
        if dest.name == 'fluxo-resumido.svg':
            src = BASE / 'docs' / 'assets' / 'fluxo-resumido.svg'
        else:
            src = ARQ
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
        ET.parse(dest)
        print('Copiado/validado', dest.relative_to(BASE))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
