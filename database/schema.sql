-- =============================================================================
-- Base CEP + Classificação Geográfica IBGE — Brasil
-- Fontes: IBGE API Localidades v1, kelvins/municipios-brasileiros, OpenCEP/Correios
-- Hierarquia: Região > UF > Mesorregião > Microrregião > Município > CEP
-- Também inclui Regiões Geográficas Intermediárias e Imediatas (classificação atual IBGE)
-- =============================================================================

PRAGMA foreign_keys = ON;

-- Macrorregiões (Norte, Nordeste, Sudeste, Sul, Centro-Oeste)
CREATE TABLE IF NOT EXISTS regioes (
    id          INTEGER PRIMARY KEY,
    sigla       TEXT    NOT NULL UNIQUE,
    nome        TEXT    NOT NULL
);

-- Unidades Federativas (27 estados + DF)
CREATE TABLE IF NOT EXISTS ufs (
    id          INTEGER PRIMARY KEY,
    sigla       TEXT    NOT NULL UNIQUE,
    nome        TEXT    NOT NULL,
    regiao_id   INTEGER NOT NULL,
    FOREIGN KEY (regiao_id) REFERENCES regioes(id)
);

-- Mesorregiões (137 no Brasil)
CREATE TABLE IF NOT EXISTS mesorregioes (
    id          INTEGER PRIMARY KEY,
    nome        TEXT    NOT NULL,
    uf_id       INTEGER NOT NULL,
    regiao_id   INTEGER NOT NULL,
    FOREIGN KEY (uf_id)     REFERENCES ufs(id),
    FOREIGN KEY (regiao_id) REFERENCES regioes(id)
);

-- Microrregiões (558 no Brasil)
CREATE TABLE IF NOT EXISTS microrregioes (
    id              INTEGER PRIMARY KEY,
    nome            TEXT    NOT NULL,
    mesorregiao_id  INTEGER NOT NULL,
    uf_id           INTEGER NOT NULL,
    regiao_id       INTEGER NOT NULL,
    FOREIGN KEY (mesorregiao_id) REFERENCES mesorregioes(id),
    FOREIGN KEY (uf_id)          REFERENCES ufs(id),
    FOREIGN KEY (regiao_id)      REFERENCES regioes(id)
);

-- Regiões Geográficas Intermediárias (classificação IBGE pós-2017)
CREATE TABLE IF NOT EXISTS regioes_intermediarias (
    id          INTEGER PRIMARY KEY,
    nome        TEXT    NOT NULL,
    uf_id       INTEGER NOT NULL,
    regiao_id   INTEGER NOT NULL,
    FOREIGN KEY (uf_id)     REFERENCES ufs(id),
    FOREIGN KEY (regiao_id) REFERENCES regioes(id)
);

-- Regiões Geográficas Imediatas
CREATE TABLE IF NOT EXISTS regioes_imediatas (
    id                      INTEGER PRIMARY KEY,
    nome                    TEXT    NOT NULL,
    regiao_intermediaria_id INTEGER NOT NULL,
    uf_id                   INTEGER NOT NULL,
    regiao_id               INTEGER NOT NULL,
    FOREIGN KEY (regiao_intermediaria_id) REFERENCES regioes_intermediarias(id),
    FOREIGN KEY (uf_id)                   REFERENCES ufs(id),
    FOREIGN KEY (regiao_id)               REFERENCES regioes(id)
);

-- Municípios (5.571)
CREATE TABLE IF NOT EXISTS municipios (
    id                      INTEGER PRIMARY KEY,
    nome                    TEXT    NOT NULL,
    microrregiao_id         INTEGER NOT NULL,
    mesorregiao_id          INTEGER NOT NULL,
    regiao_imediata_id      INTEGER,
    regiao_intermediaria_id INTEGER,
    uf_id                   INTEGER NOT NULL,
    regiao_id               INTEGER NOT NULL,
    latitude                REAL,
    longitude               REAL,
    capital                 INTEGER DEFAULT 0,
    siafi_id                TEXT,
    ddd                     INTEGER,
    fuso_horario            TEXT,
    FOREIGN KEY (microrregiao_id)         REFERENCES microrregioes(id),
    FOREIGN KEY (mesorregiao_id)          REFERENCES mesorregioes(id),
    FOREIGN KEY (regiao_imediata_id)      REFERENCES regioes_imediatas(id),
    FOREIGN KEY (regiao_intermediaria_id) REFERENCES regioes_intermediarias(id),
    FOREIGN KEY (uf_id)                   REFERENCES ufs(id),
    FOREIGN KEY (regiao_id)               REFERENCES regioes(id)
);

-- CEPs (endereços postais — popular via importar_ceps ou sincronização)
CREATE TABLE IF NOT EXISTS ceps (
    cep                 TEXT    PRIMARY KEY,
    logradouro          TEXT,
    complemento         TEXT,
    bairro              TEXT,
    municipio_nome      TEXT,
    municipio_id        INTEGER,
    uf_sigla            TEXT,
    prefixo_cep         TEXT    NOT NULL,
    ddd                 TEXT,
    siafi               TEXT,
    latitude            REAL,
    longitude           REAL,
    fonte               TEXT    DEFAULT 'import',
    atualizado_em       TEXT,
    FOREIGN KEY (municipio_id) REFERENCES municipios(id)
);

-- Faixas agregadas por cabeça de CEP (3 primeiros dígitos) — útil para roteirização
CREATE TABLE IF NOT EXISTS faixa_cep (
    prefixo_cep         TEXT    NOT NULL,
    uf_sigla            TEXT    NOT NULL,
    municipio_id        INTEGER,
    municipio_nome      TEXT,
    mesorregiao_id      INTEGER,
    mesorregiao_nome    TEXT,
    microrregiao_id     INTEGER,
    microrregiao_nome   TEXT,
    cep_min             TEXT,
    cep_max             TEXT,
    qtd_ceps            INTEGER DEFAULT 0,
    PRIMARY KEY (prefixo_cep, uf_sigla, municipio_id),
    FOREIGN KEY (municipio_id)   REFERENCES municipios(id),
    FOREIGN KEY (mesorregiao_id) REFERENCES mesorregioes(id)
);

-- Índices para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_municipios_nome       ON municipios(nome);
CREATE INDEX IF NOT EXISTS idx_municipios_uf        ON municipios(uf_id);
CREATE INDEX IF NOT EXISTS idx_municipios_meso       ON municipios(mesorregiao_id);
CREATE INDEX IF NOT EXISTS idx_municipios_micro      ON municipios(microrregiao_id);
CREATE INDEX IF NOT EXISTS idx_mesorregioes_uf       ON mesorregioes(uf_id);
CREATE INDEX IF NOT EXISTS idx_mesorregioes_nome     ON mesorregioes(nome);
CREATE INDEX IF NOT EXISTS idx_microrregioes_meso    ON microrregioes(mesorregiao_id);
CREATE INDEX IF NOT EXISTS idx_ceps_municipio        ON ceps(municipio_id);
CREATE INDEX IF NOT EXISTS idx_ceps_uf               ON ceps(uf_sigla);
CREATE INDEX IF NOT EXISTS idx_ceps_prefixo          ON ceps(prefixo_cep);
CREATE INDEX IF NOT EXISTS idx_ceps_bairro           ON ceps(bairro);
CREATE INDEX IF NOT EXISTS idx_ceps_logradouro       ON ceps(logradouro);
CREATE INDEX IF NOT EXISTS idx_faixa_cep_prefixo     ON faixa_cep(prefixo_cep);
CREATE INDEX IF NOT EXISTS idx_faixa_cep_meso        ON faixa_cep(mesorregiao_id);

-- View principal: CEP com toda a hierarquia geográfica
CREATE VIEW IF NOT EXISTS vw_cep_completo AS
SELECT
    c.cep,
    c.prefixo_cep,
    c.logradouro,
    c.complemento,
    c.bairro,
    c.municipio_nome,
    c.uf_sigla,
    c.ddd,
    c.latitude  AS cep_latitude,
    c.longitude AS cep_longitude,
    c.fonte,
    c.atualizado_em,
    m.id        AS municipio_id,
    m.nome      AS municipio_oficial,
    m.capital,
    m.latitude  AS municipio_latitude,
    m.longitude AS municipio_longitude,
    micro.id    AS microrregiao_id,
    micro.nome  AS microrregiao,
    meso.id     AS mesorregiao_id,
    meso.nome   AS mesorregiao,
    uf.id       AS uf_id,
    uf.sigla    AS uf,
    uf.nome     AS estado,
    reg.id      AS regiao_id,
    reg.sigla   AS regiao_sigla,
    reg.nome    AS regiao,
    ri.id       AS regiao_intermediaria_id,
    ri.nome     AS regiao_intermediaria,
    rim.id      AS regiao_imediata_id,
    rim.nome    AS regiao_imediata
FROM ceps c
LEFT JOIN municipios m          ON m.id = c.municipio_id
LEFT JOIN microrregioes micro   ON micro.id = m.microrregiao_id
LEFT JOIN mesorregioes meso     ON meso.id = m.mesorregiao_id
LEFT JOIN ufs uf                ON uf.id = m.uf_id
LEFT JOIN regioes reg           ON reg.id = m.regiao_id
LEFT JOIN regioes_imediatas rim ON rim.id = m.regiao_imediata_id
LEFT JOIN regioes_intermediarias ri ON ri.id = m.regiao_intermediaria_id;

-- View: municípios com hierarquia completa (sem CEP)
CREATE VIEW IF NOT EXISTS vw_municipio_completo AS
SELECT
    m.id        AS municipio_id,
    m.nome      AS municipio,
    m.capital,
    m.latitude,
    m.longitude,
    m.ddd,
    m.siafi_id,
    m.fuso_horario,
    micro.id    AS microrregiao_id,
    micro.nome  AS microrregiao,
    meso.id     AS mesorregiao_id,
    meso.nome   AS mesorregiao,
    uf.id       AS uf_id,
    uf.sigla    AS uf,
    uf.nome     AS estado,
    reg.id      AS regiao_id,
    reg.sigla   AS regiao_sigla,
    reg.nome    AS regiao,
    ri.id       AS regiao_intermediaria_id,
    ri.nome     AS regiao_intermediaria,
    rim.id      AS regiao_imediata_id,
    rim.nome    AS regiao_imediata
FROM municipios m
JOIN microrregioes micro          ON micro.id = m.microrregiao_id
JOIN mesorregioes meso            ON meso.id = m.mesorregiao_id
JOIN ufs uf                       ON uf.id = m.uf_id
JOIN regioes reg                  ON reg.id = m.regiao_id
LEFT JOIN regioes_imediatas rim   ON rim.id = m.regiao_imediata_id
LEFT JOIN regioes_intermediarias ri ON ri.id = m.regiao_intermediaria_id;

-- View: faixas de CEP com mesorregião (para roteirização logística)
CREATE VIEW IF NOT EXISTS vw_faixa_cep_mesorregiao AS
SELECT
    f.prefixo_cep,
    f.uf_sigla,
    f.municipio_nome,
    f.mesorregiao_nome AS mesorregiao,
    f.microrregiao_nome AS microrregiao,
    f.cep_min,
    f.cep_max,
    f.qtd_ceps,
    reg.sigla AS regiao_sigla,
    reg.nome  AS regiao,
    uf.nome   AS estado
FROM faixa_cep f
LEFT JOIN mesorregioes meso ON meso.id = f.mesorregiao_id
LEFT JOIN ufs uf          ON uf.sigla = f.uf_sigla
LEFT JOIN regioes reg     ON reg.id = uf.regiao_id;
