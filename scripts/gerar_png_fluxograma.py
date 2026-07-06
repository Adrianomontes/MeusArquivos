#!/usr/bin/env python3
"""Gera PNG do fluxograma para fallback mobile."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SVG_PATH = BASE / 'docs' / 'assets' / 'fluxograma-operacional-completo.svg'
HTML_PATH = BASE / 'docs' / 'assets' / '_fluxograma_render.html'
OUT_PATHS = [
    BASE / 'docs' / 'assets' / 'fluxograma-operacional-completo.png',
    BASE / 'landing-sistema-logistico' / 'assets' / 'fluxograma-operacional-completo.png',
]


def find_edge() -> str:
    for key in ('PROGRAMFILES(X86)', 'PROGRAMFILES'):
        path = os.path.join(os.environ.get(key, ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe')
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError('Microsoft Edge nao encontrado')


def main() -> int:
    svg = SVG_PATH.read_text(encoding='utf-8')
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>body{margin:0;background:#0f172a}svg{display:block;width:1040px}</style>'
        '</head><body>' + svg + '</body></html>'
    )
    HTML_PATH.write_text(html, encoding='utf-8')
    uri = HTML_PATH.as_uri()
    edge = find_edge()
    primary = OUT_PATHS[0]
    subprocess.run(
        [
            edge,
            '--headless=new',
            '--disable-gpu',
            '--hide-scrollbars',
            '--window-size=1040,3200',
            f'--screenshot={primary}',
            uri,
        ],
        check=True,
    )
    for dest in OUT_PATHS:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest != primary:
            dest.write_bytes(primary.read_bytes())
        print(f'OK {dest.relative_to(BASE)} ({dest.stat().st_size} bytes)')
    HTML_PATH.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
