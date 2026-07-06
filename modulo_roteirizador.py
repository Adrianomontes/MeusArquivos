# -*- coding: utf-8 -*-
"""Roteirizador logístico: CEP, mesorregião, cabeça de CEP, rotas e sugestão de veículo."""

import json
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import database_adapter
from modulo_cep_ibge import (
    buscar_cep_local,
    consulta_geografica,
    ensure_cep_ibge_attached,
    ensure_cep_ibge_database,
    listar_mesorregioes_ibge,
    resolver_geografia_municipio,
    resolver_mesorregiao,
    sql_mesorregiao,
    status_base_cep,
)

MODELOS_VEICULO_CONHECIDOS = (
    'FIORINO', 'KOMBI', 'VUC', 'HR', 'TOCO', 'TRUCK', 'CARRETA', 'BITRUCK',
    '3/4', '3-4', 'UTILITARIO', 'VAN', 'SPRINTER', 'DUCATO', 'MASTER',
    'ACCORD', 'SAVEIRO', 'STRADA', 'MONTANA', 'S10', 'RANGER', 'AMAROK',
)


def init_tabelas_roteirizador(conn):
    if database_adapter.is_sqlserver():
        return

    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cep_cache (
            cep TEXT PRIMARY KEY,
            logradouro TEXT,
            bairro TEXT,
            municipio TEXT,
            uf TEXT,
            ibge TEXT,
            mesoregiao TEXT,
            microregiao TEXT,
            atualizado_em TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cabeca_cep_transportadora (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prefixo_cep TEXT NOT NULL,
            municipio TEXT DEFAULT '',
            uf TEXT DEFAULT '',
            mesoregiao TEXT,
            transportadora TEXT NOT NULL,
            criado_em TEXT
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cabeca_cep_unico
        ON cabeca_cep_transportadora (prefixo_cep, municipio, uf, transportadora)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rotas_predefinidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            transportadora TEXT NOT NULL,
            observacao TEXT DEFAULT '',
            ativo INTEGER DEFAULT 1,
            criado_em TEXT,
            atualizado_em TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rotas_predefinidas_criterios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rota_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            municipio TEXT DEFAULT '',
            uf TEXT DEFAULT '',
            cep_inicio TEXT DEFAULT '',
            cep_fim TEXT DEFAULT '',
            prefixo_cep TEXT DEFAULT '',
            FOREIGN KEY (rota_id) REFERENCES rotas_predefinidas(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rotas_predefinidas_notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rota_id INTEGER NOT NULL,
            nf TEXT NOT NULL,
            acao TEXT NOT NULL,
            UNIQUE(rota_id, nf),
            FOREIGN KEY (rota_id) REFERENCES rotas_predefinidas(id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS faixa_cep_direcionamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prefixo_cep TEXT NOT NULL,
            uf TEXT DEFAULT '',
            mesoregiao TEXT DEFAULT '',
            municipio TEXT DEFAULT '',
            transportadora TEXT NOT NULL,
            criado_em TEXT
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_faixa_cep_dir_unico
        ON faixa_cep_direcionamento (prefixo_cep, uf, mesoregiao, transportadora)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rotas_saida_dia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_ref TEXT NOT NULL,
            usuario TEXT,
            payload_json TEXT NOT NULL,
            criado_em TEXT
        )
    """)
    conn.commit()


def _somente_digitos(texto):
    return re.sub(r'\D', '', str(texto or ''))


def cabeca_cep(cep):
    digits = _somente_digitos(cep)
    return digits[:3] if len(digits) >= 3 else digits


def _parse_numero_br(valor):
    if valor is None:
        return 0.0
    s = str(valor).strip().replace('R$', '').replace(' ', '')
    if not s or s.lower() in ('nan', 'none', '-', ''):
        return 0.0
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_int_br(valor):
    try:
        return int(round(_parse_numero_br(valor)))
    except (TypeError, ValueError):
        return 0


def _http_json(url, timeout=12):
    req = urllib.request.Request(url, headers={'User-Agent': 'Corax-Roteirizador/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _gravar_cep_cache(conn, registro):
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO cep_cache
        (cep, logradouro, bairro, municipio, uf, ibge, mesoregiao, microregiao, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        registro['cep'], registro.get('logradouro', ''), registro.get('bairro', ''),
        registro.get('municipio', ''), registro.get('uf', ''), registro.get('ibge', ''),
        registro.get('mesoregiao', ''), registro.get('microregiao', ''),
        registro.get('atualizado_em', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
    ))
    conn.commit()


def _enriquecer_mesorregiao_local(conn, registro):
    """Completa mesorregião/microrregião/IBGE pela base IBGE local."""
    if registro.get('mesoregiao'):
        return registro
    municipio = registro.get('municipio', '')
    uf = registro.get('uf', '')
    geo = resolver_geografia_municipio(conn, municipio, uf)
    if geo:
        registro.setdefault('mesoregiao', geo.get('mesoregiao', ''))
        registro.setdefault('microregiao', geo.get('microrregiao', ''))
        if not registro.get('ibge'):
            registro['ibge'] = str(geo.get('municipio_id', '') or '')
    if not registro.get('mesoregiao'):
        registro['mesoregiao'] = resolver_mesorregiao(
            conn, registro.get('cep', ''), municipio, uf,
        )
    return registro


def consultar_cep_web(cep, conn):
    """Consulta CEP: cache → base IBGE local → BrasilAPI + mesorregião local."""
    cep_limpo = _somente_digitos(cep)
    if len(cep_limpo) != 8:
        return None, 'CEP inválido (informe 8 dígitos).'

    cur = conn.cursor()
    cur.execute('SELECT * FROM cep_cache WHERE cep = ?', (cep_limpo,))
    cached = cur.fetchone()
    if cached:
        reg = dict(cached)
        if not reg.get('mesoregiao'):
            reg = _enriquecer_mesorregiao_local(conn, reg)
            if reg.get('mesoregiao'):
                _gravar_cep_cache(conn, reg)
        return reg, None

    local = buscar_cep_local(conn, cep_limpo)
    if local:
        local['atualizado_em'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        _gravar_cep_cache(conn, local)
        return local, None

    try:
        data = _http_json(f'https://brasilapi.com.br/api/cep/v2/{cep_limpo}')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            try:
                data = _http_json(f'https://brasilapi.com.br/api/cep/v1/{cep_limpo}')
            except Exception:
                return None, f'CEP não encontrado ({e.code}).'
        else:
            return None, f'CEP não encontrado ({e.code}).'
    except Exception as e:
        return None, f'Falha na consulta de CEP: {e}'

    municipio = data.get('city') or data.get('municipio') or ''
    uf = data.get('state') or data.get('uf') or ''
    ibge = str(data.get('city_ibge_code') or data.get('ibge') or '')
    loc = (data.get('location') or {}).get('coordinates') or {}

    registro = {
        'cep': cep_limpo,
        'logradouro': data.get('street') or data.get('logradouro') or '',
        'bairro': data.get('neighborhood') or data.get('bairro') or '',
        'municipio': municipio,
        'uf': uf,
        'ibge': ibge,
        'mesoregiao': '',
        'microregiao': '',
        'atualizado_em': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    registro = _enriquecer_mesorregiao_local(conn, registro)
    _gravar_cep_cache(conn, registro)
    return registro, None


def _resolver_coluna(cols, keywords, exclude=(), fallback_idx=None):
    for col in cols:
        nome = str(col).lower()
        if any(ex in nome for ex in exclude):
            continue
        if any(k in nome for k in keywords):
            return col
    if fallback_idx is not None and cols and 0 <= fallback_idx < len(cols):
        return cols[fallback_idx]
    return None


def extrair_modelo_veiculo(documento, col_veiculo=None, valor_veiculo=None):
    if valor_veiculo and str(valor_veiculo).strip() not in ('', '-', 'nan', 'None'):
        return str(valor_veiculo).strip().upper()

    texto = str(documento or '').upper()
    if not texto:
        return 'NÃO INFORMADO'

    if '|' in texto:
        partes = [p.strip() for p in texto.split('|') if p.strip()]
        for parte in partes[1:]:
            for modelo in MODELOS_VEICULO_CONHECIDOS:
                if modelo in parte:
                    return modelo
        if len(partes) > 1:
            return partes[1][:40]

    for modelo in MODELOS_VEICULO_CONHECIDOS:
        if modelo in texto:
            return modelo

    m = re.search(r'\b(VE[IÍ]CULO|MOD(?:ELO)?)\s*[:\-]?\s*([A-Z0-9/.\-\s]{2,30})', texto)
    if m:
        return m.group(2).strip()[:40]

    return texto[:40] if len(texto) <= 40 else texto[:40] + '…'


def chave_romaneio(documento, modelo_veiculo, motorista, data, transportadora):
    doc = str(documento or '').strip().upper()
    mod = str(modelo_veiculo or '').strip().upper()
    mot = str(motorista or '').strip().upper()
    dt = str(data or '').strip().split()[0][:10]
    tr = str(transportadora or '').strip().upper()
    return f'{doc}|{mod}|{mot}|{dt}|{tr}'


def _normalizar_data_str(valor):
    if valor is None:
        return ''
    s = str(valor).strip()
    if not s or s.lower() in ('nan', 'nat', 'none', '-'):
        return ''
    return s.split()[0][:10]


def carregar_expedicao_enriquecida(carregar_dataframe_expedicao, obter_planilha, limpar_nf, conn):
    """Lê expedição Nomus e monta índice NF → dados + histórico de romaneios."""
    caminho = obter_planilha()
    resultado = {
        'por_nf': {},
        'romaneios': {},
        'historico_veiculos': {},
    }
    if not caminho:
        return resultado

    try:
        df, col_nf, col_data, cols_orig = carregar_dataframe_expedicao(caminho)
    except Exception:
        return resultado

    cols = list(df.columns)
    col_doc = _resolver_coluna(cols, ('documento', 'doc.'), exclude=('documen',))
    col_mot = _resolver_coluna(cols, ('motor',), fallback_idx=4)
    col_transp = _resolver_coluna(cols, ('transp',), fallback_idx=3)
    col_veic = _resolver_coluna(cols, ('veic', 'model', 'placa', 'tipo ve'))

    pesos_nf = {}
    cur = conn.cursor()
    cur.execute('SELECT nf, peso_bruto_nf FROM faturamento')
    for row in cur.fetchall():
        pesos_nf[str(row[0]).strip()] = _parse_numero_br(row[1])

    romaneios = {}
    for _, r in df.iterrows():
        nf = limpar_nf(r[col_nf])
        if not nf:
            continue
        documento = str(r[col_doc]).strip() if col_doc and col_doc in r.index and r[col_doc] is not None else ''
        motorista = str(r[col_mot]).strip() if col_mot and col_mot in r.index and r[col_mot] is not None else ''
        transportadora = str(r[col_transp]).strip() if col_transp and col_transp in r.index and r[col_transp] is not None else ''
        data = _normalizar_data_str(r[col_data] if col_data in r.index else '')
        val_veic = r[col_veic] if col_veic and col_veic in r.index else None
        modelo = extrair_modelo_veiculo(documento, col_veic, val_veic)
        peso = pesos_nf.get(nf, 0.0)

        resultado['por_nf'][nf] = {
            'documento': documento,
            'motorista': motorista,
            'transportadora': transportadora,
            'data_expedicao': data,
            'modelo_veiculo': modelo,
        }

        chave = chave_romaneio(documento, modelo, motorista, data, transportadora)
        if chave not in romaneios:
            romaneios[chave] = {
                'chave': chave,
                'documento': documento,
                'modelo_veiculo': modelo,
                'motorista': motorista,
                'data': data,
                'transportadora': transportadora,
                'notas': [],
                'peso_total': 0.0,
                'qtd_notas': 0,
            }
        romaneios[chave]['notas'].append(nf)
        romaneios[chave]['peso_total'] += peso
        romaneios[chave]['qtd_notas'] += 1

    resultado['romaneios'] = romaneios

    por_modelo = {}
    for rom in romaneios.values():
        mod = rom['modelo_veiculo'] or 'NÃO INFORMADO'
        if mod not in por_modelo:
            por_modelo[mod] = {'peso_total': 0.0, 'qtd_romaneios': 0, 'qtd_notas': 0}
        por_modelo[mod]['peso_total'] += rom['peso_total']
        por_modelo[mod]['qtd_romaneios'] += 1
        por_modelo[mod]['qtd_notas'] += rom['qtd_notas']

    historico = []
    for modelo, agg in por_modelo.items():
        media = agg['peso_total'] / agg['qtd_romaneios'] if agg['qtd_romaneios'] else 0
        historico.append({
            'modelo': modelo,
            'peso_medio_romaneio': round(media, 2),
            'peso_total': round(agg['peso_total'], 2),
            'qtd_romaneios': agg['qtd_romaneios'],
            'qtd_notas': agg['qtd_notas'],
        })
    historico.sort(key=lambda x: x['qtd_romaneios'], reverse=True)
    resultado['historico_veiculos'] = historico
    return resultado


def listar_mapeamentos_cabeca_cep(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, prefixo_cep, municipio, uf, mesoregiao, transportadora, criado_em
        FROM cabeca_cep_transportadora
        ORDER BY prefixo_cep, municipio
    """)
    return [dict(r) for r in cur.fetchall()]


def salvar_mapeamento_cabeca_cep(conn, prefixo, transportadora, municipio='', uf='', mesoregiao=''):
    prefixo = _somente_digitos(prefixo)[:3]
    if len(prefixo) != 3:
        raise ValueError('Informe os 3 primeiros dígitos do CEP.')
    if not transportadora or not str(transportadora).strip():
        raise ValueError('Transportadora é obrigatória.')
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cabeca_cep_transportadora
        (prefixo_cep, municipio, uf, mesoregiao, transportadora, criado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(prefixo_cep, municipio, uf, transportadora)
        DO UPDATE SET mesoregiao = excluded.mesoregiao, criado_em = excluded.criado_em
    """, (prefixo, municipio or '', uf or '', mesoregiao or '', transportadora.strip(), agora))
    conn.commit()
    return cur.lastrowid


def _transportadora_para_nota(conn, prefixo, municipio, uf, mesoregiao, transp_faturamento, mapas):
    """Resolve transportadora: mapeamento cabeça CEP > cadastro > faturamento."""
    for m in mapas:
        if m['prefixo_cep'] != prefixo:
            continue
        if m.get('municipio') and municipio and m['municipio'].upper() != municipio.upper():
            continue
        if m.get('uf') and uf and m['uf'].upper() != uf.upper():
            continue
        return m['transportadora']
    return transp_faturamento or 'SEM TRANSPORTADORA'


def sugerir_veiculo(peso_rota, historico_veiculos):
    if not historico_veiculos or peso_rota <= 0:
        return {'modelo': 'A DEFINIR', 'peso_medio_historico': 0, 'confianca': 'baixa'}

    candidatos = sorted(historico_veiculos, key=lambda h: h['peso_medio_romaneio'])
    escolhido = candidatos[-1]
    for cand in candidatos:
        if cand['peso_medio_romaneio'] >= peso_rota * 0.85:
            escolhido = cand
            break

    diff = abs(escolhido['peso_medio_romaneio'] - peso_rota)
    confianca = 'alta' if diff <= escolhido['peso_medio_romaneio'] * 0.25 else 'media'
    if escolhido['qtd_romaneios'] < 3:
        confianca = 'baixa'

    return {
        'modelo': escolhido['modelo'],
        'peso_medio_historico': escolhido['peso_medio_romaneio'],
        'qtd_romaneios_base': escolhido['qtd_romaneios'],
        'confianca': confianca,
    }


def _mesoregiao_de_cep(conn, cep, permitir_web=False, municipio='', uf=''):
    cep_limpo = _somente_digitos(cep)
    if len(cep_limpo) != 8:
        return ''
    cur = conn.cursor()
    cur.execute('SELECT mesoregiao FROM cep_cache WHERE cep = ?', (cep_limpo,))
    row = cur.fetchone()
    if row and row[0]:
        return row[0]
    meso = resolver_mesorregiao(conn, cep_limpo, municipio, uf)
    if meso:
        return meso
    if permitir_web:
        reg, _ = consultar_cep_web(cep_limpo, conn)
        return (reg or {}).get('mesoregiao', '')
    return ''


def montar_rotas_automaticas(conn, filtros, limpar_nf, historico_veiculos):
    """
    filtros: municipio, uf, transportadora, mesoregiao, consultar_cep_web (opcional)
    """
    municipio_f = (filtros.get('municipio') or '').strip()
    uf_f = (filtros.get('uf') or '').strip().upper()
    transp_f = (filtros.get('transportadora') or '').strip().upper()
    meso_f = (filtros.get('mesoregiao') or '').strip().upper()
    permitir_web = bool(filtros.get('consultar_cep_web'))

    mapas = listar_mapeamentos_cabeca_cep(conn)
    cur = conn.cursor()
    cur.execute("""
        SELECT f.nf, f.cliente, f.municipio, f.uf, f.cep, f.transportadora,
               f.volumes, f.peso_bruto_nf, f.valor_total_nf, f.endereco,
               e.nota_fiscal AS entregue
        FROM faturamento f
        LEFT JOIN entregas_efetuadas e ON f.nf = e.nota_fiscal
    """)
    rows = cur.fetchall()

    grupos = {}
    for row in rows:
        nf = limpar_nf(row['nf'])
        if not nf:
            continue
        municipio = str(row['municipio'] or '').strip()
        uf = str(row['uf'] or '').strip().upper()
        cep = _somente_digitos(row['cep'])
        prefixo = cabeca_cep(cep)
        transp_fat = str(row['transportadora'] or '').strip()

        if municipio_f and municipio_f.upper() not in municipio.upper():
            continue
        if uf_f and uf != uf_f:
            continue

        mesoregiao = _mesoregiao_de_cep(
            conn, cep, permitir_web=permitir_web, municipio=municipio, uf=uf,
        )
        if meso_f and meso_f not in (mesoregiao or '').upper():
            continue

        transp_rota = _transportadora_para_nota(
            conn, prefixo, municipio, uf, mesoregiao, transp_fat, mapas
        )
        if transp_f and transp_f not in transp_rota.upper():
            continue

        chave_grupo = f'{transp_rota}|{municipio}|{uf}|{prefixo}'
        if chave_grupo not in grupos:
            grupos[chave_grupo] = {
                'transportadora': transp_rota,
                'municipio': municipio,
                'uf': uf,
                'prefixo_cep': prefixo,
                'mesoregiao': mesoregiao,
                'notas': [],
            }

        grupos[chave_grupo]['notas'].append({
            'nf': nf,
            'cliente': str(row['cliente'] or ''),
            'endereco': str(row['endereco'] or ''),
            'cep': cep,
            'prefixo_cep': prefixo,
            'municipio': municipio,
            'uf': uf,
            'mesoregiao': mesoregiao,
            'transportadora_faturamento': transp_fat,
            'transportadora_rota': transp_rota,
            'volumes': _parse_int_br(row['volumes']),
            'peso': _parse_numero_br(row['peso_bruto_nf']),
            'valor': _parse_numero_br(row['valor_total_nf']),
            'entregue': bool(row['entregue']),
        })

    rotas = []
    for idx, (_, grupo) in enumerate(sorted(grupos.items()), start=1):
        notas = grupo['notas']
        peso = sum(n['peso'] for n in notas)
        volumes = sum(n['volumes'] for n in notas)
        valor = sum(n['valor'] for n in notas)
        veiculo = sugerir_veiculo(peso, historico_veiculos)
        rotas.append({
            'id': f'rota-{idx}',
            'nome': f"Rota {idx} — {grupo['municipio']}/{grupo['uf']} [{grupo['prefixo_cep']}]",
            'transportadora': grupo['transportadora'],
            'municipio': grupo['municipio'],
            'uf': grupo['uf'],
            'prefixo_cep': grupo['prefixo_cep'],
            'mesoregiao': grupo['mesoregiao'],
            'notas': notas,
            'totais': {
                'valor': round(valor, 2),
                'volumes': volumes,
                'peso': round(peso, 2),
                'qtd_notas': len(notas),
            },
            'veiculo_sugerido': veiculo,
        })

    return rotas


def listar_transportadoras_faturamento(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT transportadora FROM faturamento
        WHERE transportadora IS NOT NULL AND TRIM(transportadora) != ''
        ORDER BY transportadora
    """)
    return [r[0] for r in cur.fetchall()]


def listar_municipios_faturamento(conn, uf=''):
    cur = conn.cursor()
    if uf:
        cur.execute("""
            SELECT DISTINCT municipio, uf FROM faturamento
            WHERE uf = ? AND municipio IS NOT NULL AND TRIM(municipio) != ''
            ORDER BY municipio
        """, (uf.upper(),))
    else:
        cur.execute("""
            SELECT DISTINCT municipio, uf FROM faturamento
            WHERE municipio IS NOT NULL AND TRIM(municipio) != ''
            ORDER BY uf, municipio
        """)
    return [{'municipio': r[0], 'uf': r[1]} for r in cur.fetchall()]


def _cep_norm_sql(alias='f'):
    return f"REPLACE(REPLACE(REPLACE({alias}.cep,'-',''),' ',''),'.','')"


def listar_mesoregioes_cache(conn, uf=''):
    cur = conn.cursor()
    if uf:
        cur.execute("""
            SELECT DISTINCT mesoregiao, uf FROM cep_cache
            WHERE mesoregiao IS NOT NULL AND TRIM(mesoregiao) != '' AND uf = ?
            ORDER BY mesoregiao
        """, (uf.upper(),))
    else:
        cur.execute("""
            SELECT DISTINCT mesoregiao, uf FROM cep_cache
            WHERE mesoregiao IS NOT NULL AND TRIM(mesoregiao) != ''
            ORDER BY uf, mesoregiao
        """)
    return [{'mesoregiao': r[0], 'uf': r[1]} for r in cur.fetchall()]


def listar_mesoregioes(conn, uf=''):
    """Mesorregiões oficiais IBGE (base local); complementa com cache se IBGE indisponível."""
    lista = listar_mesorregioes_ibge(conn, uf)
    if lista:
        return lista
    return listar_mesoregioes_cache(conn, uf)


def listar_bairros_faturamento_cep(conn, uf='', municipio=''):
    """Bairros disponíveis via cep_cache cruzado com faturamento."""
    cep_norm = _cep_norm_sql('f')
    where = [
        f"LENGTH({cep_norm}) >= 8",
        "c.bairro IS NOT NULL AND TRIM(c.bairro) != ''",
    ]
    params = []
    if uf:
        where.append('f.uf = ?')
        params.append(uf.upper())
    if municipio:
        where.append('UPPER(f.municipio) LIKE ?')
        params.append(f'%{municipio.strip().upper()}%')
    cur = conn.cursor()
    cur.execute(f"""
        SELECT DISTINCT c.bairro, f.municipio, f.uf
        FROM faturamento f
        INNER JOIN cep_cache c ON {cep_norm} = c.cep
        WHERE {' AND '.join(where)}
        ORDER BY f.municipio, c.bairro
    """, params)
    return [{'bairro': r[0], 'municipio': r[1], 'uf': r[2]} for r in cur.fetchall()]


def _nota_atende_criterio(municipio, uf, cep_digits, criterio):
    tipo = (criterio.get('tipo') or '').lower()
    if tipo == 'municipio':
        mun_c = (criterio.get('municipio') or '').strip().upper()
        uf_c = (criterio.get('uf') or '').strip().upper()
        if not mun_c:
            return False
        if mun_c not in (municipio or '').upper():
            return False
        if uf_c and uf_c != (uf or '').upper():
            return False
        return True
    if tipo == 'prefixo_cep':
        pref = _somente_digitos(criterio.get('prefixo_cep', ''))[:3]
        return len(pref) == 3 and len(cep_digits) >= 3 and cep_digits[:3] == pref
    if tipo == 'faixa_cep':
        ini = _somente_digitos(criterio.get('cep_inicio', ''))
        fim = _somente_digitos(criterio.get('cep_fim', ''))
        if len(ini) != 8 or len(fim) != 8 or len(cep_digits) != 8:
            return False
        if ini > fim:
            ini, fim = fim, ini
        return ini <= cep_digits <= fim
    return False


def _parse_data_iso(valor):
    s = _normalizar_data_str(valor)
    if not s:
        return ''
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s[:10], fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    if len(s) >= 10 and s[4] == '-':
        return s[:10]
    return s[:10] if len(s) >= 8 else ''


def _lista_filtro_csv(texto):
    return [x.strip().upper() for x in re.split(r'[,;|]', str(texto or '')) if x.strip()]


def carregar_nfs_expedidas(obter_planilha, carregar_expedicao_df, limpar_nf):
    """NFs presentes na planilha de expedição (consideradas expedidas)."""
    try:
        caminho = obter_planilha() if obter_planilha else None
    except Exception:
        caminho = None
    if not caminho:
        return set()
    try:
        df, col_nf, col_data, _ = carregar_expedicao_df(caminho)
        return {limpar_nf(x) for x in df[col_nf].tolist() if limpar_nf(x)}
    except Exception:
        return set()


def _nota_passa_filtros_montagem(conn, nota, filtros):
    """Aplica filtros avançados de montagem (UF, datas, CEP, meso, peso, valor…)."""
    data_ini = _parse_data_iso(filtros.get('data_inicio'))
    data_fim = _parse_data_iso(filtros.get('data_fim'))
    emissao = nota.get('emissao_iso') or ''
    if data_ini and emissao and emissao < data_ini:
        return False
    if data_fim and emissao and emissao > data_fim:
        return False

    ufs = _lista_filtro_csv(filtros.get('ufs') or filtros.get('uf'))
    if ufs and (nota.get('uf') or '').upper() not in ufs:
        return False

    municipios = _lista_filtro_csv(filtros.get('municipios') or filtros.get('municipio'))
    if municipios:
        mun_up = (nota.get('municipio') or '').upper()
        if not any(m in mun_up or mun_up in m for m in municipios):
            return False

    transps = _lista_filtro_csv(filtros.get('transportadoras') or filtros.get('transportadora'))
    if transps:
        tr_up = (nota.get('transportadora_faturamento') or '').upper()
        if not any(t in tr_up for t in transps):
            return False

    cep = nota.get('cep') or ''
    cep_ini = _somente_digitos(filtros.get('cep_inicio', ''))
    cep_fim = _somente_digitos(filtros.get('cep_fim', ''))
    if cep_ini and cep_fim and len(cep_ini) == 8 and len(cep_fim) == 8:
        if len(cep) != 8 or not (cep_ini <= cep <= cep_fim):
            return False
    pref = _somente_digitos(filtros.get('prefixo_cep', ''))[:3]
    if pref and (len(cep) < 3 or cep[:3] != pref):
        return False

    meso_f = (filtros.get('mesoregiao') or '').strip().upper()
    if meso_f:
        meso = (nota.get('mesoregiao') or '').upper()
        if meso_f not in meso:
            return False

    peso_min = _parse_numero_br(filtros.get('peso_min'))
    peso_max = _parse_numero_br(filtros.get('peso_max'))
    if peso_min > 0 and (nota.get('peso') or 0) < peso_min:
        return False
    if peso_max > 0 and (nota.get('peso') or 0) > peso_max:
        return False

    valor_min = _parse_numero_br(filtros.get('valor_min'))
    valor_max = _parse_numero_br(filtros.get('valor_max'))
    if valor_min > 0 and (nota.get('valor') or 0) < valor_min:
        return False
    if valor_max > 0 and (nota.get('valor') or 0) > valor_max:
        return False

    nf_f = (filtros.get('nf') or '').strip()
    if nf_f and nf_f not in nota.get('nf', ''):
        return False
    return True


def _enriquecer_nota_montagem(conn, nota):
    if not nota.get('mesoregiao'):
        nota['mesoregiao'] = resolver_mesorregiao(
            conn, nota.get('cep', ''), nota.get('municipio', ''), nota.get('uf', ''),
        )
    return nota


def _carregar_nota_faturamento(row, limpar_nf):
    nf = limpar_nf(row['nf'])
    if not nf:
        return None
    emissao_raw = str(row['emissao'] or '')
    return {
        'nf': nf,
        'cliente': str(row['cliente'] or ''),
        'endereco': str(row['endereco'] or ''),
        'cep': _somente_digitos(row['cep']),
        'prefixo_cep': cabeca_cep(row['cep']),
        'municipio': str(row['municipio'] or '').strip(),
        'uf': str(row['uf'] or '').strip().upper(),
        'transportadora_faturamento': str(row['transportadora'] or '').strip(),
        'volumes': _parse_int_br(row['volumes']),
        'peso': _parse_numero_br(row['peso_bruto_nf']),
        'valor': _parse_numero_br(row['valor_total_nf']),
        'emissao': emissao_raw,
        'emissao_iso': _parse_data_iso(emissao_raw),
        'entregue': bool(row['entregue']),
        'mesoregiao': '',
        'status_expedicao': 'NAO_EXPEDIDA',
    }


def listar_rotas_predefinidas(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nome, transportadora, observacao, ativo, criado_em, atualizado_em
        FROM rotas_predefinidas
        ORDER BY nome
    """)
    rotas = []
    for r in cur.fetchall():
        rota = dict(r)
        cur.execute("""
            SELECT id, tipo, municipio, uf, cep_inicio, cep_fim, prefixo_cep
            FROM rotas_predefinidas_criterios WHERE rota_id = ?
            ORDER BY id
        """, (rota['id'],))
        rota['criterios'] = [dict(c) for c in cur.fetchall()]
        cur.execute("""
            SELECT nf, acao FROM rotas_predefinidas_notas WHERE rota_id = ?
        """, (rota['id'],))
        rota['notas_manuais'] = [dict(n) for n in cur.fetchall()]
        rotas.append(rota)
    return rotas


def salvar_rota_predefinida(conn, dados):
    nome = (dados.get('nome') or '').strip()
    transportadora = (dados.get('transportadora') or '').strip()
    if not nome:
        raise ValueError('Informe o nome da rota.')
    if not transportadora:
        raise ValueError('Informe a transportadora da rota.')
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.cursor()
    rota_id = dados.get('id')
    if rota_id:
        cur.execute("""
            UPDATE rotas_predefinidas
            SET nome = ?, transportadora = ?, observacao = ?, ativo = ?, atualizado_em = ?
            WHERE id = ?
        """, (
            nome, transportadora, (dados.get('observacao') or '').strip(),
            1 if dados.get('ativo', True) else 0, agora, rota_id,
        ))
    else:
        cur.execute("""
            INSERT INTO rotas_predefinidas (nome, transportadora, observacao, ativo, criado_em, atualizado_em)
            VALUES (?, ?, ?, 1, ?, ?)
        """, (nome, transportadora, (dados.get('observacao') or '').strip(), agora, agora))
        rota_id = cur.lastrowid
    conn.commit()
    return rota_id


def excluir_rota_predefinida(conn, rota_id):
    cur = conn.cursor()
    cur.execute('DELETE FROM rotas_predefinidas_notas WHERE rota_id = ?', (rota_id,))
    cur.execute('DELETE FROM rotas_predefinidas_criterios WHERE rota_id = ?', (rota_id,))
    cur.execute('DELETE FROM rotas_predefinidas WHERE id = ?', (rota_id,))
    conn.commit()


def adicionar_criterio_rota(conn, rota_id, dados):
    tipo = (dados.get('tipo') or '').lower()
    if tipo not in ('municipio', 'faixa_cep', 'prefixo_cep'):
        raise ValueError('Tipo inválido. Use: municipio, faixa_cep ou prefixo_cep.')
    if tipo == 'municipio' and not (dados.get('municipio') or '').strip():
        raise ValueError('Informe o município.')
    if tipo == 'prefixo_cep':
        pref = _somente_digitos(dados.get('prefixo_cep', ''))[:3]
        if len(pref) != 3:
            raise ValueError('Informe os 3 primeiros dígitos do CEP.')
        dados['prefixo_cep'] = pref
    if tipo == 'faixa_cep':
        ini = _somente_digitos(dados.get('cep_inicio', ''))
        fim = _somente_digitos(dados.get('cep_fim', ''))
        if len(ini) != 8 or len(fim) != 8:
            raise ValueError('Faixa de CEP: informe CEP inicial e final com 8 dígitos.')
        dados['cep_inicio'] = ini
        dados['cep_fim'] = fim
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO rotas_predefinidas_criterios
        (rota_id, tipo, municipio, uf, cep_inicio, cep_fim, prefixo_cep)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        rota_id, tipo,
        (dados.get('municipio') or '').strip(),
        (dados.get('uf') or '').strip().upper(),
        dados.get('cep_inicio', ''),
        dados.get('cep_fim', ''),
        dados.get('prefixo_cep', ''),
    ))
    conn.commit()
    return cur.lastrowid


def remover_criterio_rota(conn, criterio_id):
    conn.execute('DELETE FROM rotas_predefinidas_criterios WHERE id = ?', (criterio_id,))
    conn.commit()


def definir_nota_rota(conn, rota_id, nf, acao):
    nf = str(nf or '').strip()
    acao = (acao or '').lower()
    if not nf:
        raise ValueError('Informe a nota fiscal.')
    if acao not in ('incluir', 'excluir', 'remover'):
        raise ValueError('Ação inválida.')
    cur = conn.cursor()
    if acao == 'remover':
        cur.execute('DELETE FROM rotas_predefinidas_notas WHERE rota_id = ? AND nf = ?', (rota_id, nf))
    else:
        cur.execute("""
            INSERT INTO rotas_predefinidas_notas (rota_id, nf, acao)
            VALUES (?, ?, ?)
            ON CONFLICT(rota_id, nf) DO UPDATE SET acao = excluded.acao
        """, (rota_id, nf, acao))
    conn.commit()


def listar_faturamento_para_rotas(conn, limpar_nf, filtros=None, nfs_expedidas=None):
    """
    Notas elegíveis para montagem: não entregues e não expedidas (planilha expedição).
    Suporta filtros de data, UF, município, CEP, mesorregião, transportadora, peso e valor.
    """
    filtros = filtros or {}
    nfs_expedidas = nfs_expedidas if nfs_expedidas is not None else set()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.nf, f.cliente, f.municipio, f.uf, f.cep, f.transportadora,
               f.volumes, f.peso_bruto_nf, f.valor_total_nf, f.endereco, f.emissao,
               e.nota_fiscal AS entregue
        FROM faturamento f
        LEFT JOIN entregas_efetuadas e ON f.nf = e.nota_fiscal
        ORDER BY f.emissao DESC, f.nf DESC
    """)
    notas = []
    for row in cur.fetchall():
        nota = _carregar_nota_faturamento(row, limpar_nf)
        if not nota:
            continue
        if nota['entregue']:
            continue
        if nota['nf'] in nfs_expedidas:
            continue
        nota = _enriquecer_nota_montagem(conn, nota)
        if not _nota_passa_filtros_montagem(conn, nota, filtros):
            continue
        notas.append(nota)
    return notas


def aplicar_rotas_predefinidas(conn, limpar_nf, filtros, historico_veiculos, nfs_expedidas=None):
    """Monta rotas a partir das regras salvas + inclusões/exclusões manuais."""
    rotas_cfg = [r for r in listar_rotas_predefinidas(conn) if r.get('ativo')]
    notas_pool = {
        n['nf']: n for n in listar_faturamento_para_rotas(
            conn, limpar_nf, filtros, nfs_expedidas=nfs_expedidas,
        )
    }
    atribuidas = {}
    rotas_saida = []

    for cfg in rotas_cfg:
        rota_id = cfg['id']
        incluir = {n['nf'] for n in cfg.get('notas_manuais', []) if n['acao'] == 'incluir'}
        excluir = {n['nf'] for n in cfg.get('notas_manuais', []) if n['acao'] == 'excluir'}
        notas_rota = []

        for nf, nota in list(notas_pool.items()):
            if nf in excluir:
                continue
            if nf in incluir or any(
                _nota_atende_criterio(nota['municipio'], nota['uf'], nota['cep'], c)
                for c in cfg.get('criterios', [])
            ):
                if nf not in atribuidas:
                    nota_copia = dict(nota)
                    nota_copia['transportadora_rota'] = cfg['transportadora']
                    notas_rota.append(nota_copia)
                    atribuidas[nf] = rota_id

        for nf in incluir:
            if nf in notas_pool and nf not in {n['nf'] for n in notas_rota}:
                nota_copia = dict(notas_pool[nf])
                nota_copia['transportadora_rota'] = cfg['transportadora']
                notas_rota.append(nota_copia)
                atribuidas[nf] = rota_id

        peso = sum(n['peso'] for n in notas_rota)
        volumes = sum(n['volumes'] for n in notas_rota)
        valor = sum(n['valor'] for n in notas_rota)
        criterios_txt = []
        for c in cfg.get('criterios', []):
            if c['tipo'] == 'municipio':
                criterios_txt.append(f"{c['municipio']}/{c['uf'] or '*'}")
            elif c['tipo'] == 'faixa_cep':
                criterios_txt.append(f"CEP {c['cep_inicio']}-{c['cep_fim']}")
            elif c['tipo'] == 'prefixo_cep':
                criterios_txt.append(f"CEP {c['prefixo_cep']}xxx")

        rotas_saida.append({
            'id': f'rota-{rota_id}',
            'rota_predefinida_id': rota_id,
            'nome': cfg['nome'],
            'transportadora': cfg['transportadora'],
            'criterios_resumo': ', '.join(criterios_txt) if criterios_txt else 'Sem critério (só notas manuais)',
            'notas': notas_rota,
            'totais': {
                'valor': round(valor, 2),
                'volumes': volumes,
                'peso': round(peso, 2),
                'qtd_notas': len(notas_rota),
            },
            'veiculo_sugerido': sugerir_veiculo(peso, historico_veiculos),
        })

    sem_rota = [n for nf, n in notas_pool.items() if nf not in atribuidas]
    return rotas_saida, sem_rota


def listar_ufs_disponiveis(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT uf FROM faturamento
        WHERE uf IS NOT NULL AND TRIM(uf) != ''
        ORDER BY uf
    """)
    return [r[0] for r in cur.fetchall()]


def sincronizar_ceps_por_uf(conn, uf, limite=100):
    uf = (uf or '').strip().upper()
    if not uf:
        raise ValueError('Informe a UF para sincronizar CEPs.')
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT REPLACE(REPLACE(REPLACE(cep, '-', ''), ' ', ''), '.', '') AS cep_limpo
        FROM faturamento
        WHERE uf = ? AND cep IS NOT NULL
          AND LENGTH(REPLACE(REPLACE(REPLACE(cep, '-', ''), ' ', ''), '.', '')) >= 8
        LIMIT ?
    """, (uf, int(limite)))
    ceps = [r[0] for r in cur.fetchall()]
    ok = err = 0
    for cep in ceps:
        reg, erro = consultar_cep_web(cep, conn)
        if reg:
            ok += 1
        else:
            err += 1
    return {'uf': uf, 'sincronizados': ok, 'erros': err, 'total': len(ceps)}


def _transportadoras_da_faixa(conn, prefixo, uf=''):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT transportadora FROM faixa_cep_direcionamento
        WHERE prefixo_cep = ? AND (uf = ? OR uf = '' OR uf IS NULL)
        ORDER BY transportadora
    """, (prefixo, uf or ''))
    lista = [r[0] for r in cur.fetchall()]
    if not lista:
        cur.execute("""
            SELECT DISTINCT transportadora FROM cabeca_cep_transportadora
            WHERE prefixo_cep = ? ORDER BY transportadora
        """, (prefixo,))
        lista = [r[0] for r in cur.fetchall()]
    return lista


def salvar_direcionamento_faixa(conn, prefixo, uf, transportadora, mesoregiao='', municipio=''):
    prefixo = _somente_digitos(prefixo)[:3]
    if len(prefixo) != 3:
        raise ValueError('Prefixo CEP inválido.')
    if not transportadora or not str(transportadora).strip():
        raise ValueError('Transportadora obrigatória.')
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO faixa_cep_direcionamento
        (prefixo_cep, uf, mesoregiao, municipio, transportadora, criado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(prefixo_cep, uf, mesoregiao, transportadora) DO NOTHING
    """, (prefixo, (uf or '').upper(), mesoregiao or '', municipio or '', transportadora.strip(), agora))
    conn.commit()


def _where_clusters_faturamento(conn, uf='', mesoregiao='', municipio='', bairro=''):
    cep_norm = _cep_norm_sql('f')
    meso_sql = sql_mesorregiao(conn)
    where = [f"LENGTH({cep_norm}) >= 8"]
    params = []
    if uf:
        where.append('f.uf = ?')
        params.append(uf.upper())
    if municipio:
        where.append('UPPER(f.municipio) LIKE ?')
        params.append(f'%{municipio.strip().upper()}%')
    if mesoregiao:
        where.append(f"UPPER(COALESCE({meso_sql}, '')) LIKE ?")
        params.append(f'%{mesoregiao.strip().upper()}%')
    if bairro:
        where.append("UPPER(COALESCE(c.bairro, '')) LIKE ?")
        params.append(f'%{bairro.strip().upper()}%')
    return cep_norm, meso_sql, where, params


def _enriquecer_totais_clusters(conn, clusters, uf='', mesoregiao='', municipio='', bairro=''):
    if not clusters:
        return clusters
    cep_norm, meso_sql, where, params = _where_clusters_faturamento(
        conn, uf, mesoregiao, municipio, bairro,
    )
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
            SUBSTR({cep_norm}, 1, 3) AS prefixo_cep,
            f.uf,
            COALESCE({meso_sql}, '') AS mesoregiao,
            f.peso_bruto_nf,
            f.valor_total_nf,
            f.volumes
        FROM faturamento f
        LEFT JOIN cep_cache c ON {cep_norm} = c.cep
        WHERE {' AND '.join(where)}
    """, params)
    totais = {}
    for row in cur.fetchall():
        chave = (row[0], row[1], row[2] or '')
        if chave not in totais:
            totais[chave] = {'peso': 0.0, 'valor': 0.0, 'volumes': 0}
        totais[chave]['peso'] += _parse_numero_br(row[3])
        totais[chave]['valor'] += _parse_numero_br(row[4])
        totais[chave]['volumes'] += _parse_int_br(row[5])
    for item in clusters:
        chave = (item['prefixo_cep'], item['uf'], item.get('_mesoregiao_raw', ''))
        t = totais.get(chave, {'peso': 0.0, 'valor': 0.0, 'volumes': 0})
        item['peso_total'] = round(t['peso'], 2)
        item['valor_total'] = round(t['valor'], 2)
        item['volumes_total'] = t['volumes']
        item.pop('_mesoregiao_raw', None)
    return clusters


def listar_clusters_cabeca_cep(conn, uf='', mesoregiao='', municipio='', bairro=''):
    cep_norm, meso_sql, where, params = _where_clusters_faturamento(
        conn, uf, mesoregiao, municipio, bairro,
    )
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
            SUBSTR({cep_norm}, 1, 3) AS prefixo_cep,
            f.uf AS uf,
            COALESCE({meso_sql}, '') AS mesoregiao,
            GROUP_CONCAT(DISTINCT f.municipio) AS municipios,
            GROUP_CONCAT(DISTINCT NULLIF(TRIM(c.bairro), '')) AS bairros,
            GROUP_CONCAT(DISTINCT NULLIF(TRIM(c.microregiao), '')) AS microregioes,
            COUNT(DISTINCT f.nf) AS qtd_notas,
            COUNT(DISTINCT f.municipio) AS qtd_municipios,
            COUNT(DISTINCT NULLIF(TRIM(c.bairro), '')) AS qtd_bairros,
            MIN({cep_norm}) AS cep_min,
            MAX({cep_norm}) AS cep_max,
            GROUP_CONCAT(DISTINCT SUBSTR(COALESCE(NULLIF(TRIM(c.logradouro), ''), f.endereco), 1, 45)) AS enderecos_amostra
        FROM faturamento f
        LEFT JOIN cep_cache c ON {cep_norm} = c.cep
        WHERE {' AND '.join(where)}
        GROUP BY prefixo_cep, f.uf, COALESCE({meso_sql}, '')
        ORDER BY prefixo_cep, mesoregiao
    """, params)

    clusters = []
    for row in cur.fetchall():
        meso_raw = row[2] or ''
        item = {
            'prefixo_cep': row[0],
            'uf': row[1],
            'mesoregiao': meso_raw or '— (sem classificação)',
            '_mesoregiao_raw': meso_raw,
            'municipios': row[3] or '',
            'bairros': row[4] or '',
            'microregioes': row[5] or '',
            'qtd_notas': row[6],
            'qtd_municipios': row[7],
            'qtd_bairros': row[8],
            'cep_min': row[9],
            'cep_max': row[10],
            'enderecos_amostra': row[11] or '',
            'faixa_cep': f"{row[9]} – {row[10]}" if row[9] and row[10] else '',
        }
        item['transportadoras'] = _transportadoras_da_faixa(conn, item['prefixo_cep'], item['uf'])
        clusters.append(item)
    return _enriquecer_totais_clusters(conn, clusters, uf, mesoregiao, municipio, bairro)


def listar_detalhe_cluster(conn, prefixo_cep, uf='', mesoregiao='', municipio='', bairro=''):
    """Detalhamento por município e bairro dentro de um cluster de cabeça CEP."""
    prefixo = _somente_digitos(prefixo_cep)[:3]
    if len(prefixo) != 3:
        return []
    cep_norm, _meso_sql, where, params = _where_clusters_faturamento(
        conn, uf, mesoregiao, municipio, bairro,
    )
    where.append(f"SUBSTR({cep_norm}, 1, 3) = ?")
    params.append(prefixo)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
            f.municipio,
            COALESCE(NULLIF(TRIM(c.bairro), ''), '—') AS bairro,
            COALESCE(NULLIF(TRIM(c.logradouro), ''), f.endereco, '—') AS logradouro,
            f.peso_bruto_nf,
            f.valor_total_nf,
            f.volumes
        FROM faturamento f
        LEFT JOIN cep_cache c ON {cep_norm} = c.cep
        WHERE {' AND '.join(where)}
    """, params)
    agg = {}
    for row in cur.fetchall():
        mun = row[0] or '—'
        bai = row[1] or '—'
        chave = (mun, bai)
        if chave not in agg:
            agg[chave] = {
                'municipio': mun,
                'bairro': bai,
                'qtd_notas': 0,
                'peso_total': 0.0,
                'valor_total': 0.0,
                'volumes_total': 0,
                'logradouros': [],
            }
        agg[chave]['qtd_notas'] += 1
        agg[chave]['peso_total'] += _parse_numero_br(row[3])
        agg[chave]['valor_total'] += _parse_numero_br(row[4])
        agg[chave]['volumes_total'] += _parse_int_br(row[5])
        log = (row[2] or '').strip()
        if log and log != '—' and log not in agg[chave]['logradouros']:
            agg[chave]['logradouros'].append(log)
    resultado = list(agg.values())
    for item in resultado:
        item['peso_total'] = round(item['peso_total'], 2)
        item['valor_total'] = round(item['valor_total'], 2)
        item['logradouros'] = ', '.join(item['logradouros'][:5])
    return sorted(resultado, key=lambda x: (-x['qtd_notas'], x['municipio'], x['bairro']))


def listar_municipios_por_uf(conn, uf):
    return listar_municipios_faturamento(conn, uf)


def salvar_rota_completa(conn, dados):
    rota_id = salvar_rota_predefinida(conn, dados)
    cur = conn.cursor()
    if dados.get('id'):
        cur.execute('DELETE FROM rotas_predefinidas_criterios WHERE rota_id = ?', (rota_id,))
        conn.commit()

    uf_rota = (dados.get('uf') or '').strip().upper()
    meso = (dados.get('mesoregiao') or '').strip()
    transp = (dados.get('transportadora') or '').strip()

    for pref in dados.get('prefixos_cep', []):
        pref = _somente_digitos(str(pref))[:3]
        if len(pref) != 3:
            continue
        adicionar_criterio_rota(conn, rota_id, {'tipo': 'prefixo_cep', 'prefixo_cep': pref, 'uf': uf_rota})
        salvar_direcionamento_faixa(conn, pref, uf_rota, transp, meso, '')

    for transp_extra in dados.get('transportadoras_extra', []):
        if transp_extra and str(transp_extra).strip():
            for pref in dados.get('prefixos_cep', []):
                pref = _somente_digitos(str(pref))[:3]
                if len(pref) == 3:
                    salvar_direcionamento_faixa(conn, pref, uf_rota, str(transp_extra).strip(), meso, '')

    for mun in dados.get('municipios', []):
        if isinstance(mun, dict):
            adicionar_criterio_rota(conn, rota_id, {
                'tipo': 'municipio',
                'municipio': mun.get('municipio', ''),
                'uf': mun.get('uf', uf_rota),
            })
    return rota_id


def _dividir_notas_por_veiculo(notas, historico):
    if not notas:
        return []
    peso_total = sum(n.get('peso', 0) for n in notas)
    veic = sugerir_veiculo(peso_total, historico)
    cap = veic.get('peso_medio_historico') or 0
    if cap <= 0 or peso_total <= cap * 1.05:
        return [notas]
    chunks, chunk, acc = [], [], 0.0
    for n in sorted(notas, key=lambda x: -(x.get('peso') or 0)):
        if chunk and acc + (n.get('peso') or 0) > cap * 1.05:
            chunks.append(chunk)
            chunk, acc = [], 0.0
        chunk.append(n)
        acc += n.get('peso') or 0
    if chunk:
        chunks.append(chunk)
    return chunks if chunks else [notas]


def montar_saida_do_dia(conn, limpar_nf, filtros, historico_veiculos, nfs_expedidas=None):
    """Aplica rotas salvas, divide por capacidade histórica de veículo e retorna colunas."""
    rotas_base, sem_rota = aplicar_rotas_predefinidas(
        conn, limpar_nf, filtros, historico_veiculos, nfs_expedidas=nfs_expedidas,
    )
    colunas = []
    idx = 0
    for rota in rotas_base:
        partes = _dividir_notas_por_veiculo(rota['notas'], historico_veiculos)
        for p_i, parte in enumerate(partes):
            idx += 1
            peso = sum(n['peso'] for n in parte)
            volumes = sum(n['volumes'] for n in parte)
            valor = sum(n['valor'] for n in parte)
            sufixo = f' · parte {p_i + 1}' if len(partes) > 1 else ''
            colunas.append({
                'id': f"col-{idx}",
                'rota_predefinida_id': rota.get('rota_predefinida_id'),
                'nome': rota['nome'] + sufixo,
                'transportadora': rota['transportadora'],
                'criterios_resumo': rota.get('criterios_resumo', ''),
                'notas': parte,
                'totais': {
                    'valor': round(valor, 2),
                    'volumes': volumes,
                    'peso': round(peso, 2),
                    'qtd_notas': len(parte),
                },
                'veiculo_sugerido': sugerir_veiculo(peso, historico_veiculos),
            })
    return colunas, sem_rota


def salvar_sessao_saida_dia(conn, usuario, rotas_payload):
    data_ref = datetime.now().strftime('%Y-%m-%d')
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO rotas_saida_dia (data_ref, usuario, payload_json, criado_em)
        VALUES (?, ?, ?, ?)
    """, (data_ref, usuario or '', json.dumps(rotas_payload, ensure_ascii=False), agora))
    conn.commit()
    return cur.lastrowid


def carregar_sessao_saida_dia(conn, data_ref=None):
    data_ref = data_ref or datetime.now().strftime('%Y-%m-%d')
    cur = conn.cursor()
    cur.execute("""
        SELECT id, payload_json, criado_em, usuario FROM rotas_saida_dia
        WHERE data_ref = ? ORDER BY id DESC LIMIT 1
    """, (data_ref,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        'id': row[0],
        'rotas': json.loads(row[1]),
        'criado_em': row[2],
        'usuario': row[3],
    }


def registrar_rotas_roteirizador(app, deps):
    """Registra rotas Flask do roteirizador. deps: get_db, login_requerido, helpers."""
    get_db = deps['get_db']
    login_requerido = deps['login_requerido']
    limpar_nf = deps['limpar_nf']
    carregar_exp = deps['carregar_expedicao']
    obter_exp = deps['obter_planilha_expedicao']

    def _nfs_exp():
        return carregar_nfs_expedidas(obter_exp, carregar_exp, limpar_nf)
    init_tabelas_roteirizador(get_db())
    ensure_cep_ibge_database()

    @app.route('/roteirizador')
    @app.route('/roteirizador/')
    @login_requerido()
    def tela_roteirizador_hub():
        from flask import render_template
        return render_template('roteirizador_hub.html')

    @app.route('/roteirizador/cadastro')
    @login_requerido()
    def tela_roteirizador_cadastro():
        from flask import render_template
        return render_template('roteirizador_cadastro.html')

    @app.route('/roteirizador/auditoria')
    @login_requerido()
    def tela_roteirizador_auditoria():
        from flask import render_template
        return render_template('roteirizador_auditoria.html')

    @app.route('/roteirizador/montagem')
    @login_requerido()
    def tela_roteirizador_montagem():
        from flask import render_template
        return render_template('roteirizador_montagem.html')

    @app.route('/api/roteirizador/ufs')
    @login_requerido()
    def api_rota_ufs():
        from flask import jsonify
        conn = get_db()
        try:
            return jsonify(listar_ufs_disponiveis(conn))
        finally:
            conn.close()

    @app.route('/api/roteirizador/sincronizar_cep', methods=['POST'])
    @login_requerido()
    def api_sincronizar_cep():
        from flask import jsonify, request
        dados = request.get_json() or {}
        conn = get_db()
        try:
            return jsonify({
                'status': 'sucesso',
                **sincronizar_ceps_por_uf(conn, dados.get('uf', ''), dados.get('limite', 100)),
            })
        except ValueError as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 400
        finally:
            conn.close()

    @app.route('/api/roteirizador/clusters')
    @login_requerido()
    def api_clusters_cep():
        from flask import jsonify, request
        conn = get_db()
        try:
            return jsonify(listar_clusters_cabeca_cep(
                conn,
                request.args.get('uf', ''),
                request.args.get('mesoregiao', ''),
                request.args.get('municipio', ''),
                request.args.get('bairro', ''),
            ))
        finally:
            conn.close()

    @app.route('/api/roteirizador/cluster_detalhe')
    @login_requerido()
    def api_cluster_detalhe():
        from flask import jsonify, request
        conn = get_db()
        try:
            return jsonify(listar_detalhe_cluster(
                conn,
                request.args.get('prefixo_cep', ''),
                request.args.get('uf', ''),
                request.args.get('mesoregiao', ''),
                request.args.get('municipio', ''),
                request.args.get('bairro', ''),
            ))
        finally:
            conn.close()

    @app.route('/api/roteirizador/bairros')
    @login_requerido()
    def api_rota_bairros():
        from flask import jsonify, request
        conn = get_db()
        try:
            return jsonify(listar_bairros_faturamento_cep(
                conn,
                request.args.get('uf', ''),
                request.args.get('municipio', ''),
            ))
        finally:
            conn.close()

    @app.route('/api/roteirizador/direcionamento_faixa', methods=['POST'])
    @login_requerido()
    def api_direcionamento_faixa():
        from flask import jsonify, request
        dados = request.get_json() or {}
        conn = get_db()
        try:
            for transp in dados.get('transportadoras', [dados.get('transportadora')]):
                if transp:
                    salvar_direcionamento_faixa(
                        conn, dados.get('prefixo_cep', ''),
                        dados.get('uf', ''), transp,
                        dados.get('mesoregiao', ''), dados.get('municipio', ''),
                    )
            return jsonify({'status': 'sucesso', 'mensagem': 'Direcionamento salvo.'})
        except ValueError as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 400
        finally:
            conn.close()

    @app.route('/api/roteirizador/rota_completa', methods=['POST'])
    @login_requerido()
    def api_salvar_rota_completa():
        from flask import jsonify, request
        conn = get_db()
        try:
            rota_id = salvar_rota_completa(conn, request.get_json() or {})
            return jsonify({'status': 'sucesso', 'id': rota_id, 'mensagem': 'Rota salva na base.'})
        except ValueError as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 400
        finally:
            conn.close()

    @app.route('/api/roteirizador/montar_saida', methods=['POST'])
    @login_requerido()
    def api_montar_saida():
        from flask import jsonify, request
        filtros = request.get_json() or {}
        conn = get_db()
        try:
            nfs_exp = _nfs_exp()
            exp = carregar_expedicao_enriquecida(carregar_exp, obter_exp, limpar_nf, conn)
            colunas, sem_rota = montar_saida_do_dia(
                conn, limpar_nf, filtros, exp['historico_veiculos'], nfs_expedidas=nfs_exp,
            )
            pool_total = len(listar_faturamento_para_rotas(
                conn, limpar_nf, filtros, nfs_expedidas=nfs_exp,
            ))
            tg = {
                'valor': round(sum(c['totais']['valor'] for c in colunas), 2),
                'volumes': sum(c['totais']['volumes'] for c in colunas),
                'peso': round(sum(c['totais']['peso'] for c in colunas), 2),
                'qtd_notas': sum(c['totais']['qtd_notas'] for c in colunas),
                'qtd_colunas': len(colunas),
                'sem_rota': len(sem_rota),
                'pool_nao_expedidas': pool_total,
                'nfs_expedidas_planilha': len(nfs_exp),
            }
            return jsonify({
                'status': 'sucesso',
                'colunas': colunas,
                'sem_rota': sem_rota,
                'total_geral': tg,
                'historico_veiculos': exp['historico_veiculos'][:12],
            })
        except Exception as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/roteirizador/salvar_saida_dia', methods=['POST'])
    @login_requerido()
    def api_salvar_saida_dia():
        from flask import jsonify, request, session
        dados = request.get_json() or {}
        conn = get_db()
        try:
            payload = {
                'colunas': dados.get('colunas', []),
                'sem_rota': dados.get('sem_rota', []),
                'filtros': dados.get('filtros', {}),
                'salvo_em': dados.get('salvo_em') or datetime.now().isoformat(timespec='seconds'),
            }
            sid = salvar_sessao_saida_dia(
                conn, session.get('usuario_nome', ''), payload,
            )
            return jsonify({'status': 'sucesso', 'id': sid, 'mensagem': 'Saída do dia registrada.'})
        finally:
            conn.close()

    @app.route('/api/roteirizador/saida_dia')
    @login_requerido()
    def api_carregar_saida_dia():
        from flask import jsonify, request
        conn = get_db()
        try:
            sess = carregar_sessao_saida_dia(conn, request.args.get('data', ''))
            if not sess:
                return jsonify({'status': 'vazio'})
            return jsonify({'status': 'sucesso', **sess})
        finally:
            conn.close()

    @app.route('/roteirizador/legado')
    @login_requerido()
    def tela_roteirizador_legado():
        from flask import render_template
        return render_template('roteirizador.html')

    @app.route('/api/roteirizador/transportadoras')
    @login_requerido()
    def api_rota_transportadoras():
        from flask import jsonify
        conn = get_db()
        try:
            return jsonify(listar_transportadoras_faturamento(conn))
        finally:
            conn.close()

    @app.route('/api/roteirizador/municipios')
    @login_requerido()
    def api_rota_municipios():
        from flask import jsonify, request
        conn = get_db()
        try:
            return jsonify(listar_municipios_faturamento(conn, request.args.get('uf', '')))
        finally:
            conn.close()

    @app.route('/api/roteirizador/mesoregioes')
    @login_requerido()
    def api_rota_mesoregioes():
        from flask import jsonify, request
        conn = get_db()
        try:
            return jsonify(listar_mesoregioes(conn, request.args.get('uf', '')))
        finally:
            conn.close()

    @app.route('/api/roteirizador/consulta_geografica')
    @login_requerido()
    def api_consulta_geografica():
        from flask import jsonify, request
        conn = get_db()
        try:
            ensure_cep_ibge_attached(conn)
            filtros = {
                'cep': request.args.get('cep', ''),
                'uf': request.args.get('uf', ''),
                'mesorregiao': request.args.get('mesoregiao', ''),
                'municipio': request.args.get('municipio', ''),
                'prefixo_cep': request.args.get('prefixo_cep', ''),
                'limite': request.args.get('limite', 200),
            }
            return jsonify({
                'status': 'sucesso',
                'base_cep': status_base_cep(),
                'resultados': consulta_geografica(conn, filtros),
            })
        finally:
            conn.close()

    @app.route('/api/roteirizador/cep/<cep>')
    @login_requerido()
    def api_rota_cep(cep):
        from flask import jsonify
        conn = get_db()
        try:
            registro, erro = consultar_cep_web(cep, conn)
            if erro:
                return jsonify({'status': 'erro', 'mensagem': erro}), 404
            return jsonify({'status': 'sucesso', 'cep': registro, 'cabeca_cep': cabeca_cep(registro['cep'])})
        finally:
            conn.close()

    @app.route('/api/roteirizador/cabeca_cep', methods=['GET'])
    @login_requerido()
    def api_listar_cabeca_cep():
        from flask import jsonify
        conn = get_db()
        try:
            return jsonify(listar_mapeamentos_cabeca_cep(conn))
        finally:
            conn.close()

    @app.route('/api/roteirizador/cabeca_cep', methods=['POST'])
    @login_requerido()
    def api_salvar_cabeca_cep():
        from flask import jsonify, request
        dados = request.get_json() or {}
        conn = get_db()
        try:
            salvar_mapeamento_cabeca_cep(
                conn,
                dados.get('prefixo_cep', ''),
                dados.get('transportadora', ''),
                dados.get('municipio', ''),
                dados.get('uf', ''),
                dados.get('mesoregiao', ''),
            )
            return jsonify({'status': 'sucesso', 'mensagem': 'Mapeamento salvo.'})
        except ValueError as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 400
        finally:
            conn.close()

    @app.route('/api/roteirizador/cabeca_cep/<int:map_id>', methods=['DELETE'])
    @login_requerido()
    def api_excluir_cabeca_cep(map_id):
        from flask import jsonify
        conn = get_db()
        try:
            conn.execute('DELETE FROM cabeca_cep_transportadora WHERE id = ?', (map_id,))
            conn.commit()
            return jsonify({'status': 'sucesso'})
        finally:
            conn.close()

    @app.route('/api/roteirizador/historico_veiculos')
    @login_requerido()
    def api_historico_veiculos():
        from flask import jsonify
        conn = get_db()
        try:
            exp = carregar_expedicao_enriquecida(carregar_exp, obter_exp, limpar_nf, conn)
            return jsonify({
                'historico': exp['historico_veiculos'],
                'qtd_romaneios': len(exp['romaneios']),
            })
        finally:
            conn.close()

    @app.route('/api/roteirizador/rotas_predefinidas', methods=['GET'])
    @login_requerido()
    def api_listar_rotas_predefinidas():
        from flask import jsonify
        conn = get_db()
        try:
            return jsonify(listar_rotas_predefinidas(conn))
        finally:
            conn.close()

    @app.route('/api/roteirizador/rotas_predefinidas', methods=['POST'])
    @login_requerido()
    def api_salvar_rota_predefinida():
        from flask import jsonify, request
        conn = get_db()
        try:
            rota_id = salvar_rota_predefinida(conn, request.get_json() or {})
            return jsonify({'status': 'sucesso', 'id': rota_id, 'mensagem': 'Rota salva.'})
        except ValueError as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 400
        finally:
            conn.close()

    @app.route('/api/roteirizador/rotas_predefinidas/<int:rota_id>', methods=['DELETE'])
    @login_requerido()
    def api_excluir_rota_predefinida(rota_id):
        from flask import jsonify
        conn = get_db()
        try:
            excluir_rota_predefinida(conn, rota_id)
            return jsonify({'status': 'sucesso'})
        finally:
            conn.close()

    @app.route('/api/roteirizador/rotas_predefinidas/<int:rota_id>/criterios', methods=['POST'])
    @login_requerido()
    def api_add_criterio_rota(rota_id):
        from flask import jsonify, request
        conn = get_db()
        try:
            cid = adicionar_criterio_rota(conn, rota_id, request.get_json() or {})
            return jsonify({'status': 'sucesso', 'id': cid})
        except ValueError as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 400
        finally:
            conn.close()

    @app.route('/api/roteirizador/criterios/<int:criterio_id>', methods=['DELETE'])
    @login_requerido()
    def api_del_criterio_rota(criterio_id):
        from flask import jsonify
        conn = get_db()
        try:
            remover_criterio_rota(conn, criterio_id)
            return jsonify({'status': 'sucesso'})
        finally:
            conn.close()

    @app.route('/api/roteirizador/rotas_predefinidas/<int:rota_id>/notas', methods=['POST'])
    @login_requerido()
    def api_nota_rota(rota_id):
        from flask import jsonify, request
        dados = request.get_json() or {}
        conn = get_db()
        try:
            definir_nota_rota(conn, rota_id, dados.get('nf', ''), dados.get('acao', 'incluir'))
            return jsonify({'status': 'sucesso'})
        except ValueError as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 400
        finally:
            conn.close()

    @app.route('/api/roteirizador/faturamento')
    @login_requerido()
    def api_faturamento_rotas():
        from flask import jsonify, request
        conn = get_db()
        try:
            filtros = {
                'data_inicio': request.args.get('data_inicio', ''),
                'data_fim': request.args.get('data_fim', ''),
                'municipio': request.args.get('municipio', ''),
                'municipios': request.args.get('municipios', ''),
                'uf': request.args.get('uf', ''),
                'ufs': request.args.get('ufs', ''),
                'nf': request.args.get('nf', ''),
                'mesoregiao': request.args.get('mesoregiao', ''),
                'transportadora': request.args.get('transportadora', ''),
                'transportadoras': request.args.get('transportadoras', ''),
                'cep_inicio': request.args.get('cep_inicio', ''),
                'cep_fim': request.args.get('cep_fim', ''),
                'prefixo_cep': request.args.get('prefixo_cep', ''),
                'peso_min': request.args.get('peso_min', ''),
                'peso_max': request.args.get('peso_max', ''),
                'valor_min': request.args.get('valor_min', ''),
                'valor_max': request.args.get('valor_max', ''),
            }
            nfs_exp = _nfs_exp()
            notas = listar_faturamento_para_rotas(conn, limpar_nf, filtros, nfs_expedidas=nfs_exp)
            return jsonify({
                'notas': notas,
                'total': len(notas),
                'criterio': 'nao_expedidas',
                'nfs_expedidas_planilha': len(nfs_exp),
            })
        finally:
            conn.close()

    @app.route('/api/roteirizador/aplicar_rotas', methods=['POST'])
    @login_requerido()
    def api_aplicar_rotas_predefinidas():
        from flask import jsonify, request
        filtros = request.get_json() or {}
        conn = get_db()
        try:
            nfs_exp = _nfs_exp()
            exp = carregar_expedicao_enriquecida(carregar_exp, obter_exp, limpar_nf, conn)
            rotas, sem_rota = aplicar_rotas_predefinidas(
                conn, limpar_nf, filtros, exp['historico_veiculos'], nfs_expedidas=nfs_exp,
            )
            total_geral = {
                'valor': round(sum(r['totais']['valor'] for r in rotas), 2),
                'volumes': sum(r['totais']['volumes'] for r in rotas),
                'peso': round(sum(r['totais']['peso'] for r in rotas), 2),
                'qtd_notas': sum(r['totais']['qtd_notas'] for r in rotas),
                'qtd_rotas': len(rotas),
                'sem_rota': len(sem_rota),
            }
            return jsonify({
                'status': 'sucesso',
                'rotas': rotas,
                'sem_rota': sem_rota,
                'total_geral': total_geral,
            })
        except Exception as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/roteirizador/montar_rotas', methods=['POST'])
    @login_requerido()
    def api_montar_rotas():
        from flask import jsonify, request
        filtros = request.get_json() or {}
        conn = get_db()
        try:
            exp = carregar_expedicao_enriquecida(carregar_exp, obter_exp, limpar_nf, conn)
            rotas = montar_rotas_automaticas(
                conn, filtros, limpar_nf, exp['historico_veiculos']
            )
            total_geral = {
                'valor': round(sum(r['totais']['valor'] for r in rotas), 2),
                'volumes': sum(r['totais']['volumes'] for r in rotas),
                'peso': round(sum(r['totais']['peso'] for r in rotas), 2),
                'qtd_notas': sum(r['totais']['qtd_notas'] for r in rotas),
                'qtd_rotas': len(rotas),
            }
            return jsonify({
                'status': 'sucesso',
                'rotas': rotas,
                'total_geral': total_geral,
                'historico_veiculos': exp['historico_veiculos'][:15],
            })
        except Exception as e:
            return jsonify({'status': 'erro', 'mensagem': str(e)}), 500
        finally:
            conn.close()

    @app.route('/api/roteirizador/sugerir_veiculo', methods=['POST'])
    @login_requerido()
    def api_sugerir_veiculo():
        from flask import jsonify, request
        dados = request.get_json() or {}
        peso = _parse_numero_br(dados.get('peso', 0))
        conn = get_db()
        try:
            exp = carregar_expedicao_enriquecida(carregar_exp, obter_exp, limpar_nf, conn)
            sug = sugerir_veiculo(peso, exp['historico_veiculos'])
            return jsonify({'status': 'sucesso', 'sugestao': sug})
        finally:
            conn.close()
