# -*- coding: utf-8 -*-
"""Injeta portal-theme.css e classes padronizadas nos templates HTML."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
SKIP = {"portal_operacional.html", "login.html", "boas_vindas.html"}
THEME = '    <link href="/static/css/portal-theme.css" rel="stylesheet">\n'
NAV_JS = '    <script src="/static/js/portal-nav.js"></script>\n'


def aplicar(caminho: Path) -> bool:
    texto = caminho.read_text(encoding="utf-8")
    if caminho.name in SKIP:
        return False
    alterou = False

    if "portal-theme.css" not in texto and "<head>" in texto:
        if "<meta charset" in texto:
            partes = texto.split("<meta charset", 1)
            resto = partes[1]
            idx = resto.find(">") + 1
            texto = partes[0] + "<meta charset" + resto[:idx] + "\n" + THEME + resto[idx:]
        else:
            texto = texto.replace("<head>", "<head>\n" + THEME, 1)
        alterou = True

    if 'class="portal-page' not in texto and "<body" in texto:
        if "<body>" in texto:
            texto = texto.replace("<body>", '<body class="portal-page embedded">', 1)
            alterou = True
        elif '<body class="' in texto and "portal-page" not in texto:
            texto = texto.replace('<body class="', '<body class="portal-page embedded ', 1)
            alterou = True

    if "portal-nav.js" not in texto and "</body>" in texto:
        texto = texto.replace("</body>", NAV_JS + "</body>", 1)
        alterou = True

    if "font-family: monospace" in texto:
        texto = texto.replace("font-family: monospace", "font-family: var(--portal-font)")
        alterou = True

    if alterou:
        caminho.write_text(texto, encoding="utf-8")
    return alterou


def main():
    total = 0
    for html in sorted(TEMPLATES.glob("*.html")):
        if aplicar(html):
            print(f"OK  {html.name}")
            total += 1
    print(f"\n{total} template(s) atualizado(s).")


if __name__ == "__main__":
    main()
