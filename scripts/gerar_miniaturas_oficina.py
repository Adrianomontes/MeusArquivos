#!/usr/bin/env python3
"""Gera miniaturas PNG das telas do Controle de Oficina Mecânica para a landing."""
from __future__ import annotations

import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, 'docs', 'controle-oficina-mecanica', 'assets', 'previews', 'html')
OUT = os.path.join(BASE, 'docs', 'controle-oficina-mecanica', 'assets', 'previews')
LANDING_OUT = os.path.join(BASE, 'landing-controle-oficina-mecanica', 'assets', 'previews')

COMMON = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  width: 640px; height: 360px; overflow: hidden;
  background: #F4F6F7; color: #2C3E50;
  font-family: 'Segoe UI', Tahoma, sans-serif; font-size: 11px;
}
.win-title {
  background: #1B2631; color: #ECF0F1; padding: 6px 12px; font-size: 11px; font-weight: 600;
}
.tabs { display: flex; background: #E5E8E8; border-bottom: 1px solid #BDC3C7; overflow: hidden; }
.tab { padding: 6px 10px; font-size: 9px; color: #566573; white-space: nowrap; }
.tab.on { background: #F4F6F7; color: #1A5276; font-weight: 700; border-top: 2px solid #2E86C1; }
.badge-demo {
  position: absolute; top: 8px; right: 8px; z-index: 2;
  font-size: 8px; font-weight: 700; letter-spacing: .05em;
  color: #f39c12; border: 1px solid #d68910; border-radius: 4px; padding: 2px 6px;
  background: rgba(27,38,49,.85);
}
.content { padding: 8px 10px; position: relative; }
fieldset {
  border: 1px solid #D5D8DC; border-radius: 4px; padding: 8px; margin-bottom: 8px;
  background: #fff;
}
legend { font-size: 9px; font-weight: 700; color: #1A5276; padding: 0 4px; }
label { font-size: 8px; color: #566573; display: block; margin-bottom: 2px; }
input, select {
  width: 100%; border: 1px solid #D5D8DC; border-radius: 3px; padding: 4px 6px;
  font-size: 9px; background: #fff; color: #2C3E50; margin-bottom: 6px;
}
.grid2 { display: grid; grid-template-columns: 1fr 90px; gap: 8px; }
.form-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px 10px; }
.logo-box {
  background: #fff; border: 1px solid #D5D8DC; border-radius: 4px; text-align: center; padding: 12px 8px;
}
.logo-box .mark { font-size: 28px; margin-bottom: 4px; }
.logo-box strong { font-size: 9px; color: #2E86C1; display: block; }
.crm { display: flex; gap: 16px; font-size: 9px; padding: 6px 0; }
.crm span { font-weight: 700; }
.crm .g { color: #27AE60; } .crm .b { color: #2E86C1; }
table { width: 100%; border-collapse: collapse; font-size: 9px; background: #fff; border: 1px solid #D5D8DC; }
th { background: #EBF5FB; color: #1A5276; padding: 5px 6px; text-align: left; font-weight: 700; }
td { padding: 4px 6px; border-top: 1px solid #EBF5FB; }
tr.alt td { background: #EBF5FB; }
.toolbar { display: flex; gap: 6px; margin: 6px 0; }
.btn { background: #E5E8E8; border: 1px solid #BDC3C7; border-radius: 3px; padding: 4px 8px; font-size: 8px; }
.btn.primary { background: #2E86C1; color: #fff; border-color: #1A5276; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: end; }
.filters .field { min-width: 100px; }
.total { margin-top: 6px; font-size: 10px; font-weight: 700; }
.total.blue { color: #1A5276; } .total.red { color: #C0392B; }
.pago { background: #D4EDDA !important; color: #155724; }
.pend { background: #fff; }
"""

PREVIEWS: dict[str, str] = {
    'cadastro_clientes': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{COMMON}</style></head><body>
<div class="win-title">Controle de Oficina Mecânica v1.2</div>
<div class="tabs">
  <div class="tab on">👥 Clientes &amp; Veículos</div>
  <div class="tab">📝 Novo Orçamento</div>
  <div class="tab">🔍 Consultar</div>
  <div class="tab">💰 Receber</div>
  <div class="tab">💸 Pagar</div>
</div>
<div class="content">
  <span class="badge-demo">DEMONSTRAÇÃO</span>
  <div class="grid2">
    <fieldset><legend>Dados do Cliente e Motorização</legend>
      <div class="form-grid">
        <div><label>Nome do Cliente *</label><input value="João Silva" readonly></div>
        <div><label>Placa *</label><input value="ABC1D23" readonly></div>
        <div><label>Marca</label><input value="Volkswagen" readonly></div>
        <div><label>Modelo/Motor</label><input value="Gol 1.0" readonly></div>
        <div><label>Ano</label><input value="2019" readonly></div>
        <div><label>Contato</label><input value="(11) 98765-4321" readonly></div>
      </div>
    </fieldset>
    <div class="logo-box"><div class="mark">🚗</div><strong>Volkswagen</strong><span style="font-size:7px;color:#95A5A6">Logo da marca</span></div>
  </div>
  <fieldset><legend>Painel Histórico do Cliente (CRM)</legend>
    <div class="crm">
      <span>Orçamentos Efetuados: <b>4</b></span>
      <span class="g">Executados: <b>3</b></span>
      <span class="b">Último: Revisão 10.000 km</span>
    </div>
  </fieldset>
  <table>
    <tr><th>ID</th><th>Nome</th><th>Placa</th><th>Marca</th><th>Modelo</th><th>Ano</th></tr>
    <tr><td>1</td><td>João Silva</td><td>ABC1D23</td><td>VW</td><td>Gol 1.0</td><td>2019</td></tr>
    <tr class="alt"><td>2</td><td>Maria Costa</td><td>XYZ9E87</td><td>Fiat</td><td>Argo</td><td>2021</td></tr>
  </table>
</div>
</body></html>""",

    'contas_receber': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{COMMON}</style></head><body>
<div class="win-title">Controle de Oficina Mecânica v1.2</div>
<div class="tabs">
  <div class="tab">👥 Clientes</div>
  <div class="tab">📝 Orçamento</div>
  <div class="tab on">💰 Contas a Receber</div>
  <div class="tab">💸 Contas a Pagar</div>
</div>
<div class="content">
  <span class="badge-demo">DEMONSTRAÇÃO</span>
  <fieldset><legend>Relatório por Período e Filtros (ENTRADAS)</legend>
    <div class="filters">
      <div class="field"><label>Mês/Ano Vencimento</label><input value="07/2026" readonly style="width:80px"></div>
      <button class="btn primary">Pesquisar e Filtrar</button>
      <button class="btn">Confirmar Baixa</button>
    </div>
  </fieldset>
  <table>
    <tr><th>ID</th><th>Nº Orç</th><th>Cliente</th><th>Parcela</th><th>Valor</th><th>Vencimento</th><th>Status</th></tr>
    <tr class="pago"><td>12</td><td>104</td><td>João Silva</td><td>1/3</td><td>R$ 450,00</td><td>05/07/2026</td><td>Recebido</td></tr>
    <tr class="pend"><td>13</td><td>104</td><td>João Silva</td><td>2/3</td><td>R$ 450,00</td><td>05/08/2026</td><td>A receber</td></tr>
    <tr class="alt pend"><td>14</td><td>108</td><td>Maria Costa</td><td>1/1</td><td>R$ 1.280,00</td><td>15/07/2026</td><td>A receber</td></tr>
  </table>
  <div class="total blue">Valores a Receber Futuros: R$ 1.730,00</div>
</div>
</body></html>""",

    'contas_pagar': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{COMMON}</style></head><body>
<div class="win-title">Controle de Oficina Mecânica v1.2</div>
<div class="tabs">
  <div class="tab">👥 Clientes</div>
  <div class="tab">🚚 Fornecedores</div>
  <div class="tab">💰 Receber</div>
  <div class="tab on">💸 Contas a Pagar</div>
</div>
<div class="content">
  <span class="badge-demo">DEMONSTRAÇÃO</span>
  <fieldset><legend>Relatório de Faturas de Fornecedores (SAÍDAS)</legend>
    <div class="filters">
      <div class="field"><label>Fornecedor</label><input value="Auto Peças Sul" readonly></div>
      <div class="field"><label>Mês/Ano</label><input value="07/2026" readonly style="width:80px"></div>
      <button class="btn primary">Pesquisar Custos</button>
      <button class="btn">Dar Baixa (Pago)</button>
    </div>
  </fieldset>
  <table>
    <tr><th>ID</th><th>Nº Orç</th><th>Fornecedor</th><th>Parcela</th><th>Item/Peça</th><th>Custo</th><th>Venc.</th><th>Status</th></tr>
    <tr class="pago"><td>8</td><td>104</td><td>Auto Peças Sul</td><td>1/1</td><td>Kit embreagem</td><td>R$ 620,00</td><td>01/07</td><td>Pago</td></tr>
    <tr class="pend"><td>9</td><td>108</td><td>Distribuidora XYZ</td><td>1/2</td><td>Pastilha freio</td><td>R$ 185,00</td><td>10/07</td><td>Aberto</td></tr>
    <tr class="alt pend"><td>10</td><td>108</td><td>Distribuidora XYZ</td><td>2/2</td><td>Óleo 5W30</td><td>R$ 92,00</td><td>10/08</td><td>Aberto</td></tr>
  </table>
  <div class="total red">Total Comprometido: R$ 277,00</div>
</div>
</body></html>""",
}


def _find_edge() -> str | None:
    for env in ('PROGRAMFILES(X86)', 'PROGRAMFILES'):
        path = os.path.join(os.environ.get(env, ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe')
        if path and os.path.isfile(path):
            return path
    return None


def main() -> int:
    os.makedirs(SRC, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(LANDING_OUT, exist_ok=True)

    edge = _find_edge()
    if not edge:
        print('[ERRO] Microsoft Edge não encontrado para gerar PNG.')
        return 1

    for nome, html in PREVIEWS.items():
        html_path = os.path.join(SRC, f'{nome}.html')
        png_path = os.path.join(OUT, f'{nome}.png')
        with open(html_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(html)

        uri = 'file:///' + html_path.replace('\\', '/')
        subprocess.run([
            edge, '--headless=new', '--disable-gpu', '--hide-scrollbars',
            '--window-size=640,360', f'--screenshot={png_path}', uri,
        ], check=True, capture_output=True)

        with open(png_path, 'rb') as src:
            data = src.read()
        for dest_dir in (OUT, LANDING_OUT):
            with open(os.path.join(dest_dir, f'{nome}.png'), 'wb') as dst:
                dst.write(data)
        print(f'  OK {nome}.png')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
