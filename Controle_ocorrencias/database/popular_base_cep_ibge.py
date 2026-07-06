# -*- coding: utf-8 -*-
"""
Popula base SQLite CEP + Mesorregião Brasil.

Fontes:
  - IBGE API Localidades v1 (regiões, UFs, meso/microrregiões, municípios)
  - kelvins/municipios-brasileiros (lat/long, DDD, SIAFI, capital)

Uso:
  python popular_base_cep_ibge.py
  python popular_base_cep_ibge.py --import-ceps caminho/ceps.csv
  python popular_base_cep_ibge.py --sync-cep 01310100 89010025
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'cep_mesorregiao_brasil.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')

IBGE_BASE = 'https://servicodados.ibge.gov.br/api/v1/localidades'
KELVINS_CSV = 'https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv'


def _http_json(url: str, timeout: int = 120):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'CEP-Mesorregiao-Builder/1.0',
        'Accept-Encoding': 'identity',
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        return json.loads(raw.decode('utf-8'))
    except UnicodeDecodeError:
        return json.loads(gzip.decompress(raw).decode('utf-8'))


def _http_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': 'CEP-Mesorregiao-Builder/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return gzip.decompress(raw).decode('utf-8')


def somente_digitos(texto) -> str:
    return re.sub(r'\D', '', str(texto or ''))


def prefixo_cep(cep: str) -> str:
    d = somente_digitos(cep)
    return d[:3] if len(d) >= 3 else d


def carregar_kelvins() -> dict:
    texto = _http_text(KELVINS_CSV)
    extra = {}
    for row in csv.DictReader(texto.splitlines()):
        cod = int(row['codigo_ibge'])
        extra[cod] = {
            'latitude': float(row['latitude']),
            'longitude': float(row['longitude']),
            'capital': int(row['capital']),
            'siafi_id': row['siafi_id'],
            'ddd': int(row['ddd']),
            'fuso_horario': row['fuso_horario'],
        }
    return extra


def baixar_ibge():
    cache = {}
    for nome in ('regioes', 'estados', 'mesorregioes', 'microrregioes', 'municipios'):
        path = os.path.join(BASE_DIR, f'_tmp_{nome}.json')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                cache[nome] = json.load(f)
                print(f'  cache {nome}: {len(cache[nome])} registros')
                continue
        print(f'  baixando {nome}...')
        cache[nome] = _http_json(f'{IBGE_BASE}/{nome}')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cache[nome], f, ensure_ascii=False)
        print(f'  OK {nome}: {len(cache[nome])} registros')
    return cache


def criar_banco(conn: sqlite3.Connection):
    with open(SCHEMA_PATH, encoding='utf-8') as f:
        conn.executescript(f.read())


def popular_ibge(conn: sqlite3.Connection, dados: dict, extra: dict):
    cur = conn.cursor()
    cur.execute('DELETE FROM faixa_cep')
    cur.execute('DELETE FROM ceps')
    cur.execute('DELETE FROM municipios')
    cur.execute('DELETE FROM regioes_imediatas')
    cur.execute('DELETE FROM regioes_intermediarias')
    cur.execute('DELETE FROM microrregioes')
    cur.execute('DELETE FROM mesorregioes')
    cur.execute('DELETE FROM ufs')
    cur.execute('DELETE FROM regioes')

    for r in dados['regioes']:
        cur.execute('INSERT INTO regioes (id, sigla, nome) VALUES (?,?,?)',
                    (r['id'], r['sigla'], r['nome']))

    for uf in dados['estados']:
        cur.execute('INSERT INTO ufs (id, sigla, nome, regiao_id) VALUES (?,?,?,?)',
                    (uf['id'], uf['sigla'], uf['nome'], uf['regiao']['id']))

    for meso in dados['mesorregioes']:
        cur.execute(
            'INSERT INTO mesorregioes (id, nome, uf_id, regiao_id) VALUES (?,?,?,?)',
            (meso['id'], meso['nome'], meso['UF']['id'], meso['UF']['regiao']['id']),
        )

    for micro in dados['microrregioes']:
        meso = micro['mesorregiao']
        cur.execute(
            'INSERT INTO microrregioes (id, nome, mesorregiao_id, uf_id, regiao_id) VALUES (?,?,?,?,?)',
            (micro['id'], micro['nome'], meso['id'], meso['UF']['id'], meso['UF']['regiao']['id']),
        )

    ri_inseridos = set()
    for mun in dados['municipios']:
        rim = mun.get('regiao-imediata') or {}
        ri = rim.get('regiao-intermediaria') or mun.get('regiao-intermediaria') or {}
        if not ri.get('id') or ri['id'] in ri_inseridos:
            continue
        uf = ri['UF']
        cur.execute(
            'INSERT OR IGNORE INTO regioes_intermediarias (id, nome, uf_id, regiao_id) VALUES (?,?,?,?)',
            (ri['id'], ri['nome'], uf['id'], uf['regiao']['id']),
        )
        ri_inseridos.add(ri['id'])

    rim_inseridos = set()
    for mun in dados['municipios']:
        rim = mun.get('regiao-imediata') or {}
        if not rim.get('id') or rim['id'] in rim_inseridos:
            continue
        ri = rim.get('regiao-intermediaria') or {}
        if not ri.get('id'):
            continue
        uf = ri['UF']
        cur.execute(
            'INSERT OR IGNORE INTO regioes_imediatas (id, nome, regiao_intermediaria_id, uf_id, regiao_id) VALUES (?,?,?,?,?)',
            (rim['id'], rim['nome'], ri['id'], uf['id'], uf['regiao']['id']),
        )
        rim_inseridos.add(rim['id'])

    # Mapa regiao-imediata -> mesorregiao/microrregiao (para municípios sem microrregião)
    rim_geo = {}
    for mun in dados['municipios']:
        micro = mun.get('microrregiao')
        if not micro:
            continue
        rim = mun.get('regiao-imediata') or {}
        if rim.get('id') and rim['id'] not in rim_geo:
            meso = micro['mesorregiao']
            uf = meso['UF']
            rim_geo[rim['id']] = (micro['id'], meso['id'], uf['id'], uf['regiao']['id'])

    for mun in dados['municipios']:
        micro = mun.get('microrregiao')
        rim = mun.get('regiao-imediata') or {}
        ri_inter = rim.get('regiao-intermediaria') or {}

        if micro:
            meso = micro['mesorregiao']
            uf = meso['UF']
            reg = uf['regiao']
            micro_id, meso_id, uf_id, reg_id = micro['id'], meso['id'], uf['id'], reg['id']
        else:
            geo = rim_geo.get(rim.get('id'))
            if not geo:
                print(f'  AVISO: município {mun["nome"]} ({mun["id"]}) sem microrregião — ignorado')
                continue
            micro_id, meso_id, uf_id, reg_id = geo
            uf_data = next(u for u in dados['estados'] if u['id'] == uf_id)
            reg = uf_data['regiao']
        ex = extra.get(mun['id'], {})
        cur.execute(
            '''INSERT INTO municipios
               (id, nome, microrregiao_id, mesorregiao_id, regiao_imediata_id,
                regiao_intermediaria_id, uf_id, regiao_id,
                latitude, longitude, capital, siafi_id, ddd, fuso_horario)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                mun['id'], mun['nome'], micro_id, meso_id,
                rim.get('id'), ri_inter.get('id'),
                uf_id, reg['id'],
                ex.get('latitude'), ex.get('longitude'),
                ex.get('capital', 0), ex.get('siafi_id'),
                ex.get('ddd'), ex.get('fuso_horario'),
            ),
        )

    conn.commit()
    print(f'  regioes: {cur.execute("SELECT COUNT(*) FROM regioes").fetchone()[0]}')
    print(f'  ufs: {cur.execute("SELECT COUNT(*) FROM ufs").fetchone()[0]}')
    print(f'  mesorregioes: {cur.execute("SELECT COUNT(*) FROM mesorregioes").fetchone()[0]}')
    print(f'  microrregioes: {cur.execute("SELECT COUNT(*) FROM microrregioes").fetchone()[0]}')
    print(f'  municipios: {cur.execute("SELECT COUNT(*) FROM municipios").fetchone()[0]}')


def resolver_municipio_id(conn: sqlite3.Connection, ibge, municipio_nome: str, uf: str):
    if ibge:
        mid = int(ibge)
        cur = conn.cursor()
        cur.execute('SELECT id FROM municipios WHERE id = ?', (mid,))
        if cur.fetchone():
            return mid
    nome = (municipio_nome or '').strip()
    uf = (uf or '').strip().upper()
    if nome and uf:
        cur = conn.cursor()
        cur.execute(
            'SELECT id FROM municipios WHERE nome = ? AND uf_id = (SELECT id FROM ufs WHERE sigla = ?)',
            (nome, uf),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            '''SELECT id FROM municipios
               WHERE uf_id = (SELECT id FROM ufs WHERE sigla = ?)
                 AND nome LIKE ? LIMIT 1''',
            (uf, nome + '%'),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    return None


def inserir_cep(conn: sqlite3.Connection, row: dict):
    cep = somente_digitos(row.get('cep', ''))
    if len(cep) != 8:
        return False
    municipio_id = resolver_municipio_id(
        conn,
        row.get('ibge') or row.get('municipio_id') or row.get('codigo_ibge'),
        row.get('localidade') or row.get('municipio_nome') or row.get('city') or '',
        row.get('uf') or row.get('uf_sigla') or row.get('state') or '',
    )

    conn.execute(
        '''INSERT OR REPLACE INTO ceps
           (cep, logradouro, complemento, bairro, municipio_nome, municipio_id,
            uf_sigla, prefixo_cep, ddd, siafi, latitude, longitude, fonte, atualizado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (
            cep,
            row.get('logradouro') or row.get('street') or '',
            row.get('complemento') or '',
            row.get('bairro') or row.get('neighborhood') or '',
            row.get('localidade') or row.get('municipio_nome') or row.get('city') or '',
            municipio_id,
            (row.get('uf') or row.get('uf_sigla') or row.get('state') or '').upper()[:2],
            prefixo_cep(cep),
            str(row.get('ddd') or ''),
            str(row.get('siafi') or row.get('gia') or ''),
            row.get('latitude'),
            row.get('longitude'),
            row.get('fonte') or row.get('source') or 'import',
            row.get('atualizado_em') or datetime.now().isoformat(timespec='seconds'),
        ),
    )
    return True


def consultar_cep_brasilapi(cep: str) -> dict | None:
    cep = somente_digitos(cep)
    try:
        data = _http_json(f'https://brasilapi.com.br/api/cep/v2/{cep}', timeout=15)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    loc = (data.get('location') or {}).get('coordinates') or {}
    return {
        'cep': cep,
        'logradouro': data.get('street', ''),
        'bairro': data.get('neighborhood', ''),
        'localidade': data.get('city', ''),
        'uf': data.get('state', ''),
        'ibge': data.get('city_ibge_code') or data.get('ibge'),
        'latitude': loc.get('latitude'),
        'longitude': loc.get('longitude'),
        'fonte': 'brasilapi',
    }


def importar_csv_ceps(conn: sqlite3.Connection, caminho: str):
    print(f'Importando CEPs de {caminho}...')
    count = 0
    with open(caminho, encoding='utf-8', errors='replace') as f:
        sample = f.read(4096)
        f.seek(0)
        delim = '|' if sample.count('|') > sample.count(',') else ','
        reader = csv.DictReader(f, delimiter=delim)
        for row in reader:
            norm = {k.strip().lower(): v for k, v in row.items()}
            mapped = {
                'cep': norm.get('cep') or norm.get('zipcode'),
                'logradouro': norm.get('logradouro') or norm.get('rua') or norm.get('street'),
                'complemento': norm.get('complemento'),
                'bairro': norm.get('bairro') or norm.get('neighborhood'),
                'localidade': norm.get('localidade') or norm.get('cidade') or norm.get('city'),
                'uf': norm.get('uf') or norm.get('estado') or norm.get('state'),
                'ibge': norm.get('ibge') or norm.get('codigo_ibge') or norm.get('city_ibge_code'),
                'ddd': norm.get('ddd'),
                'siafi': norm.get('siafi') or norm.get('gia'),
                'fonte': 'csv-import',
            }
            if inserir_cep(conn, mapped):
                count += 1
                if count % 50000 == 0:
                    conn.commit()
                    print(f'  ... {count} CEPs importados')
    conn.commit()
    print(f'  Total importado: {count} CEPs')
    recalcular_faixas(conn)


def recalcular_faixas(conn: sqlite3.Connection):
    print('Recalculando faixas de CEP (prefixo 3 dígitos)...')
    conn.execute('DELETE FROM faixa_cep')
    conn.execute('''
        INSERT INTO faixa_cep
            (prefixo_cep, uf_sigla, municipio_id, municipio_nome,
             mesorregiao_id, mesorregiao_nome, microrregiao_id, microrregiao_nome,
             cep_min, cep_max, qtd_ceps)
        SELECT
            c.prefixo_cep,
            c.uf_sigla,
            c.municipio_id,
            COALESCE(m.nome, c.municipio_nome),
            m.mesorregiao_id,
            meso.nome,
            m.microrregiao_id,
            micro.nome,
            MIN(c.cep),
            MAX(c.cep),
            COUNT(*)
        FROM ceps c
        LEFT JOIN municipios m ON m.id = c.municipio_id
        LEFT JOIN mesorregioes meso ON meso.id = m.mesorregiao_id
        LEFT JOIN microrregioes micro ON micro.id = m.microrregiao_id
        WHERE c.prefixo_cep != ''
        GROUP BY c.prefixo_cep, c.uf_sigla, c.municipio_id
    ''')
    conn.commit()
    n = conn.execute('SELECT COUNT(*) FROM faixa_cep').fetchone()[0]
    print(f'  Faixas geradas: {n}')


def sync_ceps(conn: sqlite3.Connection, lista_ceps: list[str]):
    ok = 0
    for cep in lista_ceps:
        data = consultar_cep_brasilapi(cep)
        if data and inserir_cep(conn, data):
            ok += 1
            print(f'  CEP {cep}: {data.get("localidade")}/{data.get("uf")} (IBGE {data.get("ibge")})')
        else:
            print(f'  CEP {cep}: não encontrado')
    conn.commit()
    if ok:
        recalcular_faixas(conn)


def main():
    parser = argparse.ArgumentParser(description='Popular base CEP + Mesorregião Brasil')
    parser.add_argument('--db', default=DB_PATH, help='Caminho do SQLite')
    parser.add_argument('--import-ceps', metavar='CSV', help='Importar CEPs de CSV (OpenCEP/ViaCEP)')
    parser.add_argument('--sync-cep', nargs='+', metavar='CEP', help='Sincronizar CEPs via BrasilAPI')
    parser.add_argument('--apenas-ibge', action='store_true', help='Só popular hierarquia IBGE')
    args = parser.parse_args()

    print('=== Base CEP + Mesorregião Brasil ===')
    print('Baixando dados IBGE...')
    dados = baixar_ibge()
    print('Baixando complementos kelvins/municipios-brasileiros...')
    extra = carregar_kelvins()

    if os.path.exists(args.db) and not args.import_ceps and not args.sync_cep:
        os.remove(args.db)

    conn = sqlite3.connect(args.db)
    conn.execute('PRAGMA foreign_keys = ON')
    criar_banco(conn)
    popular_ibge(conn, dados, extra)

    if args.sync_cep:
        sync_ceps(conn, args.sync_cep)
    elif args.import_ceps:
        importar_csv_ceps(conn, args.import_ceps)
    elif not args.apenas_ibge:
        exemplos = ['01310100', '20040020', '30130100', '40020000', '80010000', '89010025', '90010000']
        print('Sincronizando CEPs de exemplo via BrasilAPI...')
        sync_ceps(conn, exemplos)

    conn.close()
    print(f'\nBanco criado: {args.db}')
    print('Consultas: database/consultas_template.sql')


if __name__ == '__main__':
    main()
