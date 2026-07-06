-- =============================================================================
-- TEMPLATE DE CONSULTAS — Base CEP + Mesorregião Brasil
-- Banco: cep_mesorregiao_brasil.db (SQLite)
-- Substitua os valores entre :parametro conforme necessário
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1) CONSULTA MESTRA — CEP com todos os filtros disponíveis
-- Filtros: CEP exato, prefixo, faixa, logradouro, bairro, município, UF,
--          mesorregião, microrregião, macrorregião, capital, DDD, fonte
-- -----------------------------------------------------------------------------
SELECT *
FROM vw_cep_completo
WHERE 1 = 1
  -- CEP exato (8 dígitos, sem hífen)
  AND (:cep IS NULL OR cep = :cep)
  -- Prefixo / cabeça de CEP (3 primeiros dígitos)
  AND (:prefixo_cep IS NULL OR prefixo_cep = :prefixo_cep)
  -- Faixa de CEP
  AND (:cep_inicio IS NULL OR cep >= :cep_inicio)
  AND (:cep_fim IS NULL OR cep <= :cep_fim)
  -- Endereço
  AND (:logradouro IS NULL OR logradouro LIKE '%' || :logradouro || '%')
  AND (:bairro IS NULL OR bairro LIKE '%' || :bairro || '%')
  -- Município
  AND (:municipio IS NULL OR municipio_oficial LIKE '%' || :municipio || '%'
       OR municipio_nome LIKE '%' || :municipio || '%')
  AND (:municipio_id IS NULL OR municipio_id = :municipio_id)
  AND (:capital IS NULL OR capital = :capital)
  -- UF e macrorregião
  AND (:uf IS NULL OR uf = :uf)
  AND (:estado IS NULL OR estado LIKE '%' || :estado || '%')
  AND (:regiao_sigla IS NULL OR regiao_sigla = :regiao_sigla)
  AND (:regiao IS NULL OR regiao LIKE '%' || :regiao || '%')
  -- Mesorregião e microrregião
  AND (:mesorregiao_id IS NULL OR mesorregiao_id = :mesorregiao_id)
  AND (:mesorregiao IS NULL OR mesorregiao LIKE '%' || :mesorregiao || '%')
  AND (:microrregiao_id IS NULL OR microrregiao_id = :microrregiao_id)
  AND (:microrregiao IS NULL OR microrregiao LIKE '%' || :microrregiao || '%')
  -- Regiões geográficas IBGE (novas)
  AND (:regiao_intermediaria IS NULL OR regiao_intermediaria LIKE '%' || :regiao_intermediaria || '%')
  AND (:regiao_imediata IS NULL OR regiao_imediata LIKE '%' || :regiao_imediata || '%')
  -- Telefone / metadados
  AND (:ddd IS NULL OR ddd = :ddd)
  AND (:fonte IS NULL OR fonte = :fonte)
ORDER BY cep
LIMIT COALESCE(:limite, 500);


-- -----------------------------------------------------------------------------
-- 2) BUSCA POR CEP EXATO (uso mais comum)
-- Exemplo: WHERE cep = '01310100'
-- -----------------------------------------------------------------------------
SELECT
    cep,
    logradouro,
    complemento,
    bairro,
    municipio_oficial,
    uf,
    mesorregiao,
    microrregiao,
    regiao,
    ddd
FROM vw_cep_completo
WHERE cep = '01310100';


-- -----------------------------------------------------------------------------
-- 3) FAIXAS DE CEP POR MESORREGIÃO (roteirização logística)
-- Filtros: UF, mesorregião, prefixo, macrorregião
-- -----------------------------------------------------------------------------
SELECT
    prefixo_cep,
    uf_sigla,
    municipio_nome,
    mesorregiao,
    microrregiao,
    regiao,
    cep_min,
    cep_max,
    qtd_ceps
FROM vw_faixa_cep_mesorregiao
WHERE 1 = 1
  AND (:uf IS NULL OR uf_sigla = :uf)
  AND (:mesorregiao IS NULL OR mesorregiao LIKE '%' || :mesorregiao || '%')
  AND (:prefixo_cep IS NULL OR prefixo_cep = :prefixo_cep)
  AND (:regiao_sigla IS NULL OR regiao_sigla = :regiao_sigla)
ORDER BY prefixo_cep, municipio_nome;


-- -----------------------------------------------------------------------------
-- 4) MUNICÍPIOS POR MESORREGIÃO (sem CEP)
-- -----------------------------------------------------------------------------
SELECT *
FROM vw_municipio_completo
WHERE 1 = 1
  AND (:uf IS NULL OR uf = :uf)
  AND (:mesorregiao IS NULL OR mesorregiao LIKE '%' || :mesorregiao || '%')
  AND (:microrregiao IS NULL OR microrregiao LIKE '%' || :microrregiao || '%')
  AND (:regiao_sigla IS NULL OR regiao_sigla = :regiao_sigla)
  AND (:municipio IS NULL OR municipio LIKE '%' || :municipio || '%')
  AND (:capital IS NULL OR capital = :capital)
  AND (:ddd IS NULL OR ddd = :ddd)
ORDER BY uf, mesorregiao, municipio;


-- -----------------------------------------------------------------------------
-- 5) LISTAR TODAS AS MESORREGIÕES DO BRASIL (com contagem de municípios)
-- -----------------------------------------------------------------------------
SELECT
    reg.sigla           AS regiao,
    uf.sigla            AS uf,
    uf.nome             AS estado,
    meso.id             AS mesorregiao_id,
    meso.nome           AS mesorregiao,
    COUNT(m.id)         AS qtd_municipios,
    COUNT(DISTINCT micro.id) AS qtd_microrregioes
FROM mesorregioes meso
JOIN ufs uf         ON uf.id = meso.uf_id
JOIN regioes reg    ON reg.id = meso.regiao_id
LEFT JOIN microrregioes micro ON micro.mesorregiao_id = meso.id
LEFT JOIN municipios m        ON m.mesorregiao_id = meso.id
GROUP BY meso.id
ORDER BY reg.sigla, uf.sigla, meso.nome;


-- -----------------------------------------------------------------------------
-- 6) MESORREGIÕES DE UMA UF ESPECÍFICA
-- Exemplo: SP → 15 mesorregiões
-- -----------------------------------------------------------------------------
SELECT id, nome
FROM mesorregioes
WHERE uf_id = (SELECT id FROM ufs WHERE sigla = 'SP')
ORDER BY nome;


-- -----------------------------------------------------------------------------
-- 7) CEPs DE UMA MESORREGIÃO INTEIRA
-- -----------------------------------------------------------------------------
SELECT c.*
FROM vw_cep_completo c
WHERE c.mesorregiao_id = (
    SELECT id FROM mesorregioes
    WHERE nome LIKE '%Campinas%' AND uf_id = (SELECT id FROM ufs WHERE sigla = 'SP')
)
ORDER BY c.cep;


-- -----------------------------------------------------------------------------
-- 8) AGRUPAMENTO: quantidade de CEPs por mesorregião e UF
-- -----------------------------------------------------------------------------
SELECT
    reg.sigla       AS regiao,
    uf.sigla        AS uf,
    meso.nome       AS mesorregiao,
    COUNT(c.cep)    AS total_ceps,
    COUNT(DISTINCT c.prefixo_cep) AS total_prefixos,
    MIN(c.cep)      AS cep_minimo,
    MAX(c.cep)      AS cep_maximo
FROM mesorregioes meso
JOIN ufs uf      ON uf.id = meso.uf_id
JOIN regioes reg ON reg.id = meso.regiao_id
LEFT JOIN municipios m ON m.mesorregiao_id = meso.id
LEFT JOIN ceps c       ON c.municipio_id = m.id
GROUP BY meso.id
HAVING (:uf IS NULL OR uf.sigla = :uf)
   AND (:mesorregiao IS NULL OR meso.nome LIKE '%' || :mesorregiao || '%')
ORDER BY total_ceps DESC;


-- -----------------------------------------------------------------------------
-- 9) BUSCA POR PREFIXO (cabeça de CEP) — ex: 013xxx em SP
-- -----------------------------------------------------------------------------
SELECT
    prefixo_cep,
    uf,
    municipio_oficial,
    mesorregiao,
    COUNT(*) AS qtd,
    GROUP_CONCAT(DISTINCT bairro) AS bairros
FROM vw_cep_completo
WHERE prefixo_cep = '013'
  AND uf = 'SP'
GROUP BY prefixo_cep, uf, municipio_oficial, mesorregiao;


-- -----------------------------------------------------------------------------
-- 10) CRUZAMENTO: município IBGE → mesorregião (sem precisar de CEP)
-- Útil para classificar notas fiscais pelo código IBGE do destinatário
-- -----------------------------------------------------------------------------
SELECT
    m.id            AS codigo_ibge,
    m.nome          AS municipio,
    uf.sigla        AS uf,
    meso.nome       AS mesorregiao,
    micro.nome      AS microrregiao,
    reg.nome        AS regiao,
    rim.nome        AS regiao_imediata,
    ri.nome         AS regiao_intermediaria
FROM municipios m
JOIN ufs uf               ON uf.id = m.uf_id
JOIN mesorregioes meso      ON meso.id = m.mesorregiao_id
JOIN microrregioes micro    ON micro.id = m.microrregiao_id
JOIN regioes reg            ON reg.id = m.regiao_id
LEFT JOIN regioes_imediatas rim ON rim.id = m.regiao_imediata_id
LEFT JOIN regioes_intermediarias ri ON ri.id = m.regiao_intermediaria_id
WHERE m.id = 3550308;  -- São Paulo/SP


-- -----------------------------------------------------------------------------
-- 11) CONSULTA PARAMETRIZADA PRONTA PARA PYTHON/FLASK
-- Copie e use com sqlite3 + dict de parâmetros
-- -----------------------------------------------------------------------------
/*
params = {
    'cep': None,
    'prefixo_cep': '013',
    'cep_inicio': None,
    'cep_fim': None,
    'logradouro': None,
    'bairro': None,
    'municipio': None,
    'municipio_id': None,
    'capital': None,
    'uf': 'SP',
    'estado': None,
    'regiao_sigla': None,
    'regiao': None,
    'mesorregiao_id': None,
    'mesorregiao': 'Metropolitana de São Paulo',
    'microrregiao_id': None,
    'microrregiao': None,
    'regiao_intermediaria': None,
    'regiao_imediata': None,
    'ddd': None,
    'fonte': None,
    'limite': 100,
}
*/


-- -----------------------------------------------------------------------------
-- 12) EXEMPLO MYSQL/POSTGRESQL — mesma lógica, sintaxe adaptada
-- -----------------------------------------------------------------------------
/*
SELECT *
FROM vw_cep_completo
WHERE (:cep::text IS NULL OR cep = :cep)
  AND (:prefixo_cep::text IS NULL OR prefixo_cep = :prefixo_cep)
  AND (:uf::text IS NULL OR uf = :uf)
  AND (:mesorregiao::text IS NULL OR mesorregiao ILIKE '%' || :mesorregiao || '%')
  AND (:bairro::text IS NULL OR bairro ILIKE '%' || :bairro || '%')
ORDER BY cep
LIMIT COALESCE(:limite::int, 500);
*/


-- -----------------------------------------------------------------------------
-- 13) VALIDAR: CEP pertence à mesorregião esperada?
-- -----------------------------------------------------------------------------
SELECT
    CASE WHEN mesorregiao LIKE '%Campinas%' THEN 'SIM' ELSE 'NAO' END AS pertence_mesorregiao,
    vw.*
FROM vw_cep_completo vw
WHERE cep = '13010000';


-- -----------------------------------------------------------------------------
-- 14) EXPORTAR LISTA DE MESORREGIÕES PARA DROPDOWN (como no roteirizador)
-- -----------------------------------------------------------------------------
SELECT
    meso.id || '|' || uf.sigla AS valor,
    uf.sigla || ' — ' || meso.nome AS rotulo
FROM mesorregioes meso
JOIN ufs uf ON uf.id = meso.uf_id
ORDER BY uf.sigla, meso.nome;
