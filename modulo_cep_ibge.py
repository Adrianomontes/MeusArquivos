# -*- coding: utf-8 -*-
"""Acesso à base local CEP + mesorregião IBGE (database/cep_mesorregiao_brasil.db)."""

from __future__ import annotations

import os
import re
import sqlite3
import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CEP_DB_PATH = os.path.join(BASE_DIR, 'database', 'cep_mesorregiao_brasil.db')
CEP_IBGE_ALIAS = 'cep_ibge'
_popular_script = os.path.join(BASE_DIR, 'database', 'popular_base_cep_ibge.py')


def somente_digitos(texto) -> str:
    return re.sub(r'\D', '', str(texto or ''))


def cep_db_existe() -> bool:
    return os.path.isfile(CEP_DB_PATH) and os.path.getsize(CEP_DB_PATH) > 50_000


def _conn_cep_ibge():
    conn = sqlite3.connect(CEP_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_cep_ibge_database() -> bool:
    """Garante que o SQLite IBGE existe; tenta gerar se ausente."""
    if cep_db_existe():
        return True
    if not os.path.isfile(_popular_script):
        return False
    try:
        import subprocess
        subprocess.run(
            [sys.executable, _popular_script, '--apenas-ibge'],
            cwd=BASE_DIR,
            timeout=180,
            check=False,
        )
    except Exception:
        return False
    return cep_db_existe()


def _ja_anexado(conn: sqlite3.Connection) -> bool:
    cur = conn.cursor()
    cur.execute('PRAGMA database_list')
    return any(row[1] == CEP_IBGE_ALIAS for row in cur.fetchall())


def ensure_cep_ibge_attached(conn: sqlite3.Connection) -> bool:
    if not cep_db_existe():
        ensure_cep_ibge_database()
    if not cep_db_existe():
        return False
    if _ja_anexado(conn):
        return True
    try:
        conn.execute(f"ATTACH DATABASE ? AS {CEP_IBGE_ALIAS}", (CEP_DB_PATH,))
        return True
    except sqlite3.Error:
        return False


def expr_mesorregiao_enriquecida(f_alias='f', c_alias='c') -> str:
    """Expressão SQL — requer ATTACH cep_ibge na conexão."""
    cep_norm = (
        f"REPLACE(REPLACE(REPLACE({f_alias}.cep,'-',''),' ',''),'.','')"
    )
    return f"""COALESCE(
        NULLIF(TRIM({c_alias}.mesoregiao), ''),
        (SELECT vm.mesorregiao FROM {CEP_IBGE_ALIAS}.vw_municipio_completo vm
         WHERE vm.uf = {f_alias}.uf
           AND UPPER(vm.municipio) = UPPER(TRIM({f_alias}.municipio))
         LIMIT 1),
        (SELECT fc.mesorregiao_nome FROM {CEP_IBGE_ALIAS}.faixa_cep fc
         WHERE fc.uf_sigla = {f_alias}.uf
           AND fc.prefixo_cep = SUBSTR({cep_norm}, 1, 3)
         LIMIT 1),
        (SELECT meso.nome FROM {CEP_IBGE_ALIAS}.mesorregioes meso
         JOIN {CEP_IBGE_ALIAS}.municipios mun ON mun.mesorregiao_id = meso.id
         JOIN {CEP_IBGE_ALIAS}.ufs u ON u.id = mun.uf_id
         WHERE u.sigla = {f_alias}.uf
           AND UPPER(mun.nome) LIKE UPPER(TRIM({f_alias}.municipio)) || '%'
         LIMIT 1)
    )"""


def sql_mesorregiao(conn: sqlite3.Connection, f_alias='f', c_alias='c') -> str:
    if ensure_cep_ibge_attached(conn):
        return expr_mesorregiao_enriquecida(f_alias, c_alias)
    return f"COALESCE(NULLIF(TRIM({c_alias}.mesoregiao), ''), '')"


def buscar_cep_local(conn: sqlite3.Connection, cep: str) -> dict | None:
    cep = somente_digitos(cep)
    if len(cep) != 8 or not ensure_cep_ibge_attached(conn):
        return None
    cur = conn.cursor()
    cur.execute(f"""
        SELECT cep, logradouro, complemento, bairro, municipio_oficial, uf,
               mesorregiao, microrregiao, municipio_id, ddd, regiao
        FROM {CEP_IBGE_ALIAS}.vw_cep_completo
        WHERE cep = ?
        LIMIT 1
    """, (cep,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        'cep': row[0],
        'logradouro': row[1] or '',
        'complemento': row[2] or '',
        'bairro': row[3] or '',
        'municipio': row[4] or '',
        'uf': row[5] or '',
        'mesoregiao': row[6] or '',
        'microregiao': row[7] or '',
        'ibge': str(row[8] or ''),
        'ddd': str(row[9] or ''),
        'regiao': row[10] or '',
        'fonte': 'cep_ibge_local',
    }


def resolver_geografia_municipio(conn: sqlite3.Connection, municipio: str, uf: str) -> dict | None:
    municipio = (municipio or '').strip()
    uf = (uf or '').strip().upper()
    if not municipio or not uf or not ensure_cep_ibge_attached(conn):
        return None
    cur = conn.cursor()
    cur.execute(f"""
        SELECT municipio_id, municipio, uf, mesorregiao, microrregiao, regiao,
               regiao_intermediaria, regiao_imediata, ddd, latitude, longitude
        FROM {CEP_IBGE_ALIAS}.vw_municipio_completo
        WHERE uf = ? AND UPPER(municipio) = UPPER(?)
        LIMIT 1
    """, (uf, municipio))
    row = cur.fetchone()
    if not row:
        cur.execute(f"""
            SELECT municipio_id, municipio, uf, mesorregiao, microrregiao, regiao,
                   regiao_intermediaria, regiao_imediata, ddd, latitude, longitude
            FROM {CEP_IBGE_ALIAS}.vw_municipio_completo
            WHERE uf = ? AND UPPER(municipio) LIKE UPPER(?) || '%'
            LIMIT 1
        """, (uf, municipio))
        row = cur.fetchone()
    if not row:
        return None
    return {
        'municipio_id': row[0],
        'municipio': row[1],
        'uf': row[2],
        'mesoregiao': row[3] or '',
        'microrregiao': row[4] or '',
        'regiao': row[5] or '',
        'regiao_intermediaria': row[6] or '',
        'regiao_imediata': row[7] or '',
        'ddd': row[8],
        'latitude': row[9],
        'longitude': row[10],
    }


def resolver_mesorregiao(conn: sqlite3.Connection, cep: str, municipio: str = '', uf: str = '') -> str:
    cep = somente_digitos(cep)
    if len(cep) == 8:
        local = buscar_cep_local(conn, cep)
        if local and local.get('mesoregiao'):
            return local['mesoregiao']
    if municipio and uf:
        geo = resolver_geografia_municipio(conn, municipio, uf)
        if geo and geo.get('mesoregiao'):
            return geo['mesoregiao']
    if len(cep) >= 3 and uf and ensure_cep_ibge_attached(conn):
        prefixo = cep[:3]
        cur = conn.cursor()
        cur.execute(f"""
            SELECT mesorregiao_nome FROM {CEP_IBGE_ALIAS}.faixa_cep
            WHERE prefixo_cep = ? AND uf_sigla = ?
            LIMIT 1
        """, (prefixo, uf.upper()))
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
    return ''


def listar_mesorregioes_ibge(conn: sqlite3.Connection, uf: str = '') -> list[dict]:
    if not ensure_cep_ibge_attached(conn):
        return []
    uf = (uf or '').strip().upper()
    cur = conn.cursor()
    if uf:
        cur.execute(f"""
            SELECT meso.nome AS mesoregiao, uf.sigla AS uf
            FROM {CEP_IBGE_ALIAS}.mesorregioes meso
            JOIN {CEP_IBGE_ALIAS}.ufs uf ON uf.id = meso.uf_id
            WHERE uf.sigla = ?
            ORDER BY meso.nome
        """, (uf,))
    else:
        cur.execute(f"""
            SELECT meso.nome AS mesoregiao, uf.sigla AS uf
            FROM {CEP_IBGE_ALIAS}.mesorregioes meso
            JOIN {CEP_IBGE_ALIAS}.ufs uf ON uf.id = meso.uf_id
            ORDER BY uf.sigla, meso.nome
        """)
    return [{'mesoregiao': r[0], 'uf': r[1]} for r in cur.fetchall()]


def consulta_geografica(conn: sqlite3.Connection, filtros: dict) -> list[dict]:
    """Consulta avançada na base IBGE (CEP ou município)."""
    if not ensure_cep_ibge_attached(conn):
        return []
    cep = somente_digitos(filtros.get('cep', ''))
    uf = (filtros.get('uf') or '').strip().upper()
    mesorregiao = (filtros.get('mesorregiao') or '').strip()
    municipio = (filtros.get('municipio') or '').strip()
    prefixo = somente_digitos(filtros.get('prefixo_cep', ''))[:3]
    limite = min(int(filtros.get('limite') or 200), 1000)

    if cep and len(cep) == 8:
        local = buscar_cep_local(conn, cep)
        return [local] if local else []

    where = ['1=1']
    params: list = []
    if uf:
        where.append('vm.uf = ?')
        params.append(uf)
    if mesorregiao:
        where.append('UPPER(vm.mesorregiao) LIKE ?')
        params.append(f'%{mesorregiao.upper()}%')
    if municipio:
        where.append('UPPER(vm.municipio) LIKE ?')
        params.append(f'%{municipio.upper()}%')

    cur = conn.cursor()
    cur.execute(f"""
        SELECT vm.municipio_id, vm.municipio, vm.uf, vm.estado, vm.mesorregiao,
               vm.microrregiao, vm.regiao, vm.ddd, vm.latitude, vm.longitude
        FROM {CEP_IBGE_ALIAS}.vw_municipio_completo vm
        WHERE {' AND '.join(where)}
        ORDER BY vm.uf, vm.mesorregiao, vm.municipio
        LIMIT ?
    """, params + [limite])
    rows = [
        {
            'municipio_id': r[0], 'municipio': r[1], 'uf': r[2], 'estado': r[3],
            'mesorregiao': r[4], 'microrregiao': r[5], 'regiao': r[6],
            'ddd': r[7], 'latitude': r[8], 'longitude': r[9],
        }
        for r in cur.fetchall()
    ]

    if prefixo and uf:
        cur.execute(f"""
            SELECT prefixo_cep, uf_sigla, municipio_nome, mesorregiao_nome,
                   microrregiao_nome, cep_min, cep_max, qtd_ceps
            FROM {CEP_IBGE_ALIAS}.faixa_cep
            WHERE prefixo_cep = ? AND uf_sigla = ?
        """, (prefixo, uf))
        faixas = [
            {
                'prefixo_cep': r[0], 'uf': r[1], 'municipio': r[2],
                'mesorregiao': r[3], 'microrregiao': r[4],
                'cep_min': r[5], 'cep_max': r[6], 'qtd_ceps': r[7],
            }
            for r in cur.fetchall()
        ]
        if faixas:
            return faixas
    return rows


def status_base_cep() -> dict:
    return {
        'caminho': CEP_DB_PATH,
        'existe': cep_db_existe(),
        'tamanho_kb': round(os.path.getsize(CEP_DB_PATH) / 1024, 1) if cep_db_existe() else 0,
    }
