#!/usr/bin/env python3
"""Gera miniaturas PNG dos módulos para a landing (dados fictícios)."""
from __future__ import annotations

import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, 'landing-sistema-logistico', 'assets', 'previews', 'html')
OUT = os.path.join(BASE, 'landing-sistema-logistico', 'assets', 'previews')
DOCS_OUT = os.path.join(BASE, 'docs', 'assets', 'previews')

COMMON = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  width: 640px; height: 360px; overflow: hidden;
  background: #0f172a; color: #f8fafc;
  font-family: 'Segoe UI', system-ui, sans-serif; font-size: 11px;
}
.hdr {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid #334155;
  background: #1e293b;
}
.hdr h1 { font-size: 13px; color: #38bdf8; font-weight: 800; }
.badge-demo {
  font-size: 9px; font-weight: 700; letter-spacing: .06em;
  color: #f59e0b; border: 1px solid #b45309; border-radius: 4px; padding: 2px 6px;
}
"""

PREVIEWS: dict[str, str] = {
    'estoque': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 8px; padding: 12px; }}
.kpi {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px; border-left: 3px solid #38bdf8; }}
.kpi span {{ color: #94a3b8; font-size: 9px; text-transform: uppercase; }}
.kpi strong {{ display: block; font-size: 18px; margin-top: 4px; }}
table {{ width: calc(100% - 24px); margin: 0 12px; border-collapse: collapse; }}
th, td {{ padding: 6px 8px; border-bottom: 1px solid #334155; text-align: left; }}
th {{ color: #38bdf8; background: #162032; font-size: 9px; }}
td {{ color: #cbd5e1; }}
</style></head><body>
<div class="hdr"><h1>📦 Saldo de estoque</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<div class="grid">
  <div class="kpi"><span>SKUs ativos</span><strong>1.248</strong></div>
  <div class="kpi"><span>Posições</span><strong>86%</strong></div>
  <div class="kpi"><span>Rupturas</span><strong>12</strong></div>
  <div class="kpi"><span>Giro 30d</span><strong>4,2x</strong></div>
</div>
<table>
<tr><th>Item</th><th>EAN</th><th>Saldo</th><th>Curva</th></tr>
<tr><td>Produto demo A</td><td>7891000001</td><td>420</td><td>A</td></tr>
<tr><td>Produto demo B</td><td>7891000002</td><td>188</td><td>B</td></tr>
<tr><td>Produto demo C</td><td>7891000003</td><td>64</td><td>C</td></tr>
</table>
</body></html>""",

    'wms': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.wrap {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 12px; }}
.panel {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px; }}
label {{ display: block; color: #38bdf8; font-size: 9px; font-weight: 700; margin-bottom: 4px; }}
input, select {{ width: 100%; background: #0f172a; border: 1px solid #475569; color: #fff; border-radius: 4px; padding: 6px; margin-bottom: 8px; }}
.btn {{ background: #10b981; color: #fff; border: none; border-radius: 6px; padding: 8px; font-weight: 700; width: 100%; }}
.list {{ margin-top: 8px; }}
.row {{ display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #334155; color: #cbd5e1; }}
</style></head><body>
<div class="hdr"><h1>📝 Lançar contagem WMS</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<div class="wrap">
  <div class="panel">
    <label>POSIÇÃO</label><input value="A-12-03" readonly>
    <label>SKU / EAN</label><input value="7892000456" readonly>
    <label>QTD CONTADA</label><input value="24" readonly>
    <button class="btn">Confirmar apontamento</button>
  </div>
  <div class="panel">
    <div style="color:#94a3b8;font-size:9px;margin-bottom:6px;">ÚLTIMOS APONTAMENTOS</div>
    <div class="list">
      <div class="row"><span>B-04-01</span><span>12 un</span></div>
      <div class="row"><span>C-08-02</span><span>6 un</span></div>
      <div class="row"><span>A-12-03</span><span>24 un</span></div>
    </div>
  </div>
</div>
</body></html>""",

    'faturamento': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.bar {{ display:flex; gap:8px; padding:10px 12px; }}
.pill {{ background:#1e293b; border:1px solid #334155; border-radius:999px; padding:4px 10px; color:#94a3b8; font-size:9px; }}
.chart {{ margin: 0 12px; height: 120px; background: linear-gradient(180deg,#1e293b,#0f172a); border:1px solid #334155; border-radius:8px; display:flex; align-items:flex-end; gap:6px; padding:10px; }}
.bar-c {{ flex:1; background:#38bdf8; border-radius:4px 4px 0 0; opacity:.85; }}
table {{ width: calc(100% - 24px); margin: 10px 12px 0; border-collapse: collapse; }}
th, td {{ padding: 5px 8px; border-bottom: 1px solid #334155; }}
th {{ color:#38bdf8; font-size:9px; }} td {{ color:#cbd5e1; }}
.ok {{ color:#10b981; font-weight:700; }}
</style></head><body>
<div class="hdr"><h1>💸 Faturamento conciliado</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<div class="bar"><span class="pill">NF-e 142</span><span class="pill">Expedidas 128</span><span class="pill">Pendentes 14</span></div>
<div class="chart">
  <div class="bar-c" style="height:45%"></div><div class="bar-c" style="height:70%"></div>
  <div class="bar-c" style="height:55%"></div><div class="bar-c" style="height:90%"></div>
  <div class="bar-c" style="height:60%"></div><div class="bar-c" style="height:80%"></div>
</div>
<table>
<tr><th>NF</th><th>Cliente demo</th><th>Status</th></tr>
<tr><td>000.142.001</td><td>Cliente A</td><td class="ok">Entregue</td></tr>
<tr><td>000.142.002</td><td>Cliente B</td><td class="ok">Em rota</td></tr>
</table>
</body></html>""",

    'rotas': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.sub {{ padding: 8px 14px; color:#94a3b8; font-size:10px; }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; padding:0 12px 12px; }}
.card {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:10px; }}
.card h2 {{ color:#38bdf8; font-size:11px; margin-bottom:4px; }}
.card p {{ color:#94a3b8; font-size:9px; line-height:1.4; }}
.map {{ margin:0 12px; height:110px; border-radius:8px; border:1px solid #334155;
  background: repeating-linear-gradient(90deg,#1e293b 0 20px,#162032 20px 40px); position:relative; }}
.dot {{ position:absolute; width:8px; height:8px; background:#10b981; border-radius:50%; }}
</style></head><body>
<div class="hdr"><h1>🗺️ Roteirizador</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<p class="sub">CEP · mesorregião · montagem da saída</p>
<div class="grid">
  <div class="card"><h2>Cadastro</h2><p>Faixas e transportadoras</p></div>
  <div class="card"><h2>Auditoria</h2><p>Clusters por praça</p></div>
  <div class="card"><h2>Montagem</h2><p>Saída do dia</p></div>
</div>
<div class="map"><span class="dot" style="left:18%;top:40%"></span><span class="dot" style="left:45%;top:55%"></span><span class="dot" style="left:72%;top:30%"></span></div>
</body></html>""",

    'expedicao': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.cols {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; padding:12px; }}
.lane {{ background:#1e293b; border:1px solid #334155; border-radius:8px; min-height:200px; padding:8px; }}
.lane h3 {{ font-size:10px; color:#38bdf8; margin-bottom:8px; }}
.note {{ background:#0f172a; border:1px solid #475569; border-radius:6px; padding:6px; margin-bottom:6px; color:#e2e8f0; font-size:9px; }}
.tag {{ display:inline-block; background:#2563eb; color:#fff; border-radius:4px; padding:1px 4px; font-size:8px; margin-top:4px; }}
</style></head><body>
<div class="hdr"><h1>📦 Expedição multimodal</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<div class="cols">
  <div class="lane"><h3>Próprio</h3><div class="note">NF 000.201<br><span class="tag">Rota 03</span></div></div>
  <div class="lane"><h3>Contratada</h3><div class="note">NF 000.202<br><span class="tag" style="background:#8b5cf6">Transp. demo</span></div></div>
  <div class="lane"><h3>FOB / Retira</h3><div class="note">NF 000.203<br><span class="tag" style="background:#f59e0b">Cliente retira</span></div></div>
</div>
</body></html>""",

    'canhotos': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.wrap {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; padding:12px; }}
.box {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:10px; }}
.sig {{ height:120px; border:2px dashed #475569; border-radius:8px; margin-top:8px;
  display:flex; align-items:center; justify-content:center; color:#64748b; font-style:italic; }}
.cam {{ width:100%; height:90px; background:#0f172a; border-radius:8px; border:1px solid #334155;
  display:flex; align-items:center; justify-content:center; color:#38bdf8; font-size:28px; }}
</style></head><body>
<div class="hdr"><h1>✍️ Baixa mobile / canhoto</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<div class="wrap">
  <div class="box">
    <div style="color:#94a3b8;font-size:9px;">NF 000.305 · Cliente demo</div>
    <div class="sig">Assinatura do recebedor</div>
    <div style="margin-top:8px;color:#10b981;font-weight:700;">✔ Pronto para enviar</div>
  </div>
  <div class="box">
    <div class="cam">📸</div>
    <div style="margin-top:8px;color:#94a3b8;font-size:9px;">Foto do canhoto (opcional)</div>
  </div>
</div>
</body></html>""",

    'excecoes': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.form {{ padding:12px; display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
.field label {{ display:block; color:#38bdf8; font-size:9px; margin-bottom:3px; }}
.field input, .field select {{ width:100%; background:#1e293b; border:1px solid #475569; color:#fff; border-radius:4px; padding:6px; }}
.table {{ margin:0 12px; border:1px solid #334155; border-radius:8px; overflow:hidden; }}
tr:nth-child(even) td {{ background:#162032; }}
th, td {{ padding:6px 8px; border-bottom:1px solid #334155; }}
th {{ background:#0f172a; color:#38bdf8; font-size:9px; }}
</style></head><body>
<div class="hdr"><h1>🚚 Devoluções / ocorrências</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<div class="form">
  <div class="field"><label>NF</label><input value="000.901" readonly></div>
  <div class="field"><label>Motivo</label><select><option>Avaria transporte</option></select></div>
  <div class="field"><label>Status</label><input value="Em análise" readonly></div>
</div>
<table class="table" style="width:calc(100% - 24px); border-collapse:collapse; margin:8px 12px;">
<tr><th>Data</th><th>NF</th><th>Motivo</th></tr>
<tr><td>06/07/2026</td><td>000.901</td><td>Avaria</td></tr>
<tr><td>05/07/2026</td><td>000.880</td><td>Recusa</td></tr>
</table>
</body></html>""",

    'frete': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.grid {{ display:grid; grid-template-columns:1.2fr .8fr; gap:10px; padding:12px; }}
.panel {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:10px; }}
label {{ color:#38bdf8; font-size:9px; font-weight:700; }}
input {{ width:100%; margin-top:4px; margin-bottom:8px; background:#0f172a; border:1px solid #475569; color:#fff; border-radius:4px; padding:6px; }}
.sla {{ display:inline-block; padding:4px 8px; border-radius:999px; font-size:9px; font-weight:700; }}
.sla-ok {{ background:#064e3b; color:#6ee7b7; }}
.sla-warn {{ background:#78350f; color:#fcd34d; }}
</style></head><body>
<div class="hdr"><h1>🚛 Coletas FOB / frete</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<div class="grid">
  <div class="panel">
    <label>TRANSPORTADORA</label><input value="Transportadora demo LTDA" readonly>
    <label>PRAZO COLETA</label><input value="08/07/2026" readonly>
    <label>VOLUME FOB</label><input value="18 m³ · 6 pallets" readonly>
  </div>
  <div class="panel">
    <div style="margin-bottom:8px;"><span class="sla sla-ok">No prazo</span></div>
    <div style="margin-bottom:8px;"><span class="sla sla-warn">Atenção SLA</span></div>
    <div style="color:#94a3b8;font-size:9px;">Farol operacional de coletas pendentes</div>
  </div>
</div>
</body></html>""",

    'indicadores': f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{COMMON}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; padding:12px; }}
.kpi {{ background:#1e293b; border:1px solid #334155; border-left:3px solid #3b82f6; border-radius:8px; padding:8px; }}
.kpi span {{ color:#94a3b8; font-size:8px; text-transform:uppercase; }}
.kpi strong {{ font-size:16px; display:block; margin-top:2px; }}
.chart {{ margin:0 12px; height:150px; background:#1e293b; border:1px solid #334155; border-radius:8px; padding:10px; position:relative; }}
.line {{ position:absolute; left:10px; right:10px; bottom:24px; height:2px; background:linear-gradient(90deg,#38bdf8,#10b981); border-radius:2px; }}
</style></head><body>
<div class="hdr"><h1>🗼 Torre de controle</h1><span class="badge-demo">DEMONSTRAÇÃO</span></div>
<div class="kpis">
  <div class="kpi"><span>OTIF</span><strong>94%</strong></div>
  <div class="kpi"><span>Lead time</span><strong>1,8d</strong></div>
  <div class="kpi"><span>Canhotos</span><strong>87%</strong></div>
  <div class="kpi"><span>FOB pend.</span><strong>6</strong></div>
</div>
<div class="chart"><div class="line"></div><div style="position:absolute;bottom:8px;left:10px;color:#64748b;font-size:9px;">Indicadores demo · sem dados reais</div></div>
</body></html>""",
}


def _find_edge() -> str | None:
    paths = [
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ]
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def main() -> int:
    os.makedirs(SRC, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DOCS_OUT, exist_ok=True)

    edge = _find_edge()
    if not edge:
        print('[ERRO] Microsoft Edge não encontrado para gerar PNG.')
        return 1

    for nome, html in PREVIEWS.items():
        html_path = os.path.join(SRC, f'{nome}.html')
        png_path = os.path.join(OUT, f'{nome}.png')
        docs_png = os.path.join(DOCS_OUT, f'{nome}.png')
        with open(html_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(html)

        uri = 'file:///' + html_path.replace('\\', '/')
        cmd = [
            edge,
            '--headless=new',
            '--disable-gpu',
            '--hide-scrollbars',
            f'--window-size=640,360',
            f'--screenshot={png_path}',
            uri,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        with open(png_path, 'rb') as src, open(docs_png, 'wb') as dst:
            dst.write(src.read())
        print(f'  OK {nome}.png')

    print(f'\nMiniaturas em: {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
