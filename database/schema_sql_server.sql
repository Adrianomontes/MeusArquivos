/*
  Schema inicial SQL Server - Sistema Logistico

  Uso sugerido em banco vazio:
    sqlcmd -S .\SQLEXPRESS -d SistemaLogistico -E -i database\schema_sql_server.sql
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID('dbo.usuarios_sistema', 'U') IS NULL
CREATE TABLE dbo.usuarios_sistema (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nome NVARCHAR(255) NOT NULL,
    login NVARCHAR(120) NOT NULL UNIQUE,
    senha_hash NVARCHAR(255) NOT NULL,
    nivel_hierarquico NVARCHAR(50) NOT NULL
);
GO

IF OBJECT_ID('dbo.logs_auditoria', 'U') IS NULL
CREATE TABLE dbo.logs_auditoria (
    id INT IDENTITY(1,1) PRIMARY KEY,
    data_hora NVARCHAR(30) NOT NULL,
    usuario NVARCHAR(255) NOT NULL,
    nivel NVARCHAR(50) NOT NULL,
    acao NVARCHAR(255) NOT NULL,
    detalhes NVARCHAR(MAX) NULL
);
GO

IF OBJECT_ID('dbo.configuracoes_painel', 'U') IS NULL
CREATE TABLE dbo.configuracoes_painel (
    chave NVARCHAR(120) PRIMARY KEY,
    valor NVARCHAR(MAX) NULL
);
GO

IF OBJECT_ID('dbo.faturamento', 'U') IS NULL
CREATE TABLE dbo.faturamento (
    nf NVARCHAR(80) PRIMARY KEY,
    emissao NVARCHAR(80) NULL,
    cliente NVARCHAR(500) NULL,
    endereco NVARCHAR(500) NULL,
    municipio NVARCHAR(255) NULL,
    uf NVARCHAR(10) NULL,
    cep NVARCHAR(30) NULL,
    transportadora NVARCHAR(255) NULL,
    modalidade NVARCHAR(120) NULL,
    volumes NVARCHAR(80) NULL,
    especie NVARCHAR(120) NULL,
    peso_bruto_nf NVARCHAR(80) NULL,
    pedido NVARCHAR(120) NULL,
    valor_total_nf NVARCHAR(80) NULL
);
GO

IF OBJECT_ID('dbo.faturamento_itens', 'U') IS NULL
CREATE TABLE dbo.faturamento_itens (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nf NVARCHAR(80) NULL,
    codigo_item NVARCHAR(120) NULL,
    descricao_item NVARCHAR(800) NULL,
    qtde NVARCHAR(80) NULL,
    um NVARCHAR(50) NULL,
    peso_unitario NVARCHAR(80) NULL,
    peso_total NVARCHAR(80) NULL
);
GO

IF OBJECT_ID('dbo.entregas_efetuadas', 'U') IS NULL
CREATE TABLE dbo.entregas_efetuadas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nota_fiscal NVARCHAR(80) NULL,
    data_entrega NVARCHAR(40) NULL,
    recebedor NVARCHAR(255) NULL,
    assinatura NVARCHAR(MAX) NULL
);
GO

IF OBJECT_ID('dbo.canhotos', 'U') IS NULL
CREATE TABLE dbo.canhotos (
    id INT IDENTITY(1,1) PRIMARY KEY,
    cliente NVARCHAR(500) NULL,
    nota_fiscal NVARCHAR(80) NULL,
    data_recebimento NVARCHAR(40) NULL,
    status NVARCHAR(80) NULL,
    observacoes NVARCHAR(MAX) NULL
);
GO

IF OBJECT_ID('dbo.canhotos_digitais', 'U') IS NULL
CREATE TABLE dbo.canhotos_digitais (
    id INT IDENTITY(1,1) PRIMARY KEY,
    motorista NVARCHAR(255) NOT NULL,
    rg NVARCHAR(80) NOT NULL,
    transportadora NVARCHAR(255) NOT NULL,
    assinatura_base64 NVARCHAR(MAX) NOT NULL,
    data_hora NVARCHAR(40) NOT NULL,
    nota_fiscal NVARCHAR(80) NULL,
    usuario_baixa NVARCHAR(255) NULL
);
GO

IF OBJECT_ID('dbo.devolucoes', 'U') IS NULL
CREATE TABLE dbo.devolucoes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nota_fiscal NVARCHAR(80) NOT NULL,
    data_devolucao NVARCHAR(40) NOT NULL,
    transportadora NVARCHAR(255) NULL,
    ocorrencia NVARCHAR(255) NOT NULL,
    cte_devolucao NVARCHAR(120) NULL,
    responsavel_recebimento NVARCHAR(255) NULL,
    detalhes_livre NVARCHAR(MAX) NULL,
    nome_recebedor NVARCHAR(255) NULL,
    nota_devolucao_cliente NVARCHAR(120) NULL,
    imagem_base64 NVARCHAR(MAX) NULL
);
GO

IF OBJECT_ID('dbo.coletas', 'U') IS NULL
CREATE TABLE dbo.coletas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    cliente NVARCHAR(500) NULL,
    nota_fiscal NVARCHAR(80) NULL,
    transportadora NVARCHAR(255) NULL,
    data_solicitacao NVARCHAR(40) NULL,
    status NVARCHAR(80) NULL,
    tratativa NVARCHAR(MAX) NULL,
    motivo NVARCHAR(500) NULL,
    prazo_coleta NVARCHAR(80) NULL,
    transp_coleta NVARCHAR(255) NULL,
    contato_celular NVARCHAR(80) NULL,
    contato_email NVARCHAR(255) NULL,
    tipo_registro NVARCHAR(80) NULL
);
GO

IF OBJECT_ID('dbo.ocorrencias', 'U') IS NULL
CREATE TABLE dbo.ocorrencias (
    id INT IDENTITY(1,1) PRIMARY KEY,
    cliente NVARCHAR(500) NULL,
    nota_fiscal NVARCHAR(80) NULL,
    data NVARCHAR(40) NULL,
    tratativa NVARCHAR(MAX) NULL,
    motivo NVARCHAR(500) NULL,
    prazo_coleta NVARCHAR(80) NULL,
    transp_coleta NVARCHAR(255) NULL,
    contato_celular NVARCHAR(80) NULL,
    contato_email NVARCHAR(255) NULL
);
GO

IF OBJECT_ID('dbo.transportadoras', 'U') IS NULL
CREATE TABLE dbo.transportadoras (
    id INT IDENTITY(1,1) PRIMARY KEY,
    name NVARCHAR(255) NULL,
    telefone NVARCHAR(80) NULL,
    responsavel NVARCHAR(255) NULL,
    telephone NVARCHAR(80) NULL
);
GO

IF OBJECT_ID('dbo.motivos_ocorrencias', 'U') IS NULL
CREATE TABLE dbo.motivos_ocorrencias (
    id INT IDENTITY(1,1) PRIMARY KEY,
    motivo NVARCHAR(500) NOT NULL
);
GO

IF OBJECT_ID('dbo.metas_diarias', 'U') IS NULL
CREATE TABLE dbo.metas_diarias (
    data NVARCHAR(20) PRIMARY KEY,
    valor_meta DECIMAL(18,2) NULL
);
GO

IF OBJECT_ID('dbo.cep_cache', 'U') IS NULL
CREATE TABLE dbo.cep_cache (
    cep NVARCHAR(20) PRIMARY KEY,
    logradouro NVARCHAR(500) NULL,
    bairro NVARCHAR(255) NULL,
    municipio NVARCHAR(255) NULL,
    uf NVARCHAR(10) NULL,
    ibge NVARCHAR(40) NULL,
    mesoregiao NVARCHAR(255) NULL,
    microregiao NVARCHAR(255) NULL,
    atualizado_em NVARCHAR(40) NULL
);
GO

IF OBJECT_ID('dbo.cabeca_cep_transportadora', 'U') IS NULL
CREATE TABLE dbo.cabeca_cep_transportadora (
    id INT IDENTITY(1,1) PRIMARY KEY,
    prefixo_cep NVARCHAR(10) NOT NULL,
    municipio NVARCHAR(255) NULL DEFAULT '',
    uf NVARCHAR(10) NULL DEFAULT '',
    mesoregiao NVARCHAR(255) NULL,
    transportadora NVARCHAR(255) NOT NULL,
    criado_em NVARCHAR(40) NULL
);
GO

IF OBJECT_ID('dbo.faixa_cep_direcionamento', 'U') IS NULL
CREATE TABLE dbo.faixa_cep_direcionamento (
    id INT IDENTITY(1,1) PRIMARY KEY,
    prefixo_cep NVARCHAR(10) NOT NULL,
    uf NVARCHAR(10) NULL DEFAULT '',
    mesoregiao NVARCHAR(255) NULL DEFAULT '',
    municipio NVARCHAR(255) NULL DEFAULT '',
    transportadora NVARCHAR(255) NOT NULL,
    criado_em NVARCHAR(40) NULL
);
GO

IF OBJECT_ID('dbo.rotas_predefinidas', 'U') IS NULL
CREATE TABLE dbo.rotas_predefinidas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nome NVARCHAR(255) NOT NULL,
    transportadora NVARCHAR(255) NOT NULL,
    observacao NVARCHAR(MAX) NULL DEFAULT '',
    ativo INT NULL DEFAULT 1,
    criado_em NVARCHAR(40) NULL,
    atualizado_em NVARCHAR(40) NULL
);
GO

IF OBJECT_ID('dbo.rotas_predefinidas_criterios', 'U') IS NULL
CREATE TABLE dbo.rotas_predefinidas_criterios (
    id INT IDENTITY(1,1) PRIMARY KEY,
    rota_id INT NOT NULL,
    tipo NVARCHAR(80) NOT NULL,
    municipio NVARCHAR(255) NULL DEFAULT '',
    uf NVARCHAR(10) NULL DEFAULT '',
    cep_inicio NVARCHAR(20) NULL DEFAULT '',
    cep_fim NVARCHAR(20) NULL DEFAULT '',
    prefixo_cep NVARCHAR(10) NULL DEFAULT ''
);
GO

IF OBJECT_ID('dbo.rotas_predefinidas_notas', 'U') IS NULL
CREATE TABLE dbo.rotas_predefinidas_notas (
    id INT IDENTITY(1,1) PRIMARY KEY,
    rota_id INT NOT NULL,
    nf NVARCHAR(80) NOT NULL,
    acao NVARCHAR(40) NOT NULL
);
GO

IF OBJECT_ID('dbo.rotas_saida_dia', 'U') IS NULL
CREATE TABLE dbo.rotas_saida_dia (
    id INT IDENTITY(1,1) PRIMARY KEY,
    data_ref NVARCHAR(20) NOT NULL,
    usuario NVARCHAR(255) NULL,
    payload_json NVARCHAR(MAX) NOT NULL,
    criado_em NVARCHAR(40) NULL
);
GO

IF OBJECT_ID('dbo.de_para_modais', 'U') IS NULL
CREATE TABLE dbo.de_para_modais (
    transportadora NVARCHAR(255) PRIMARY KEY,
    modal_correto NVARCHAR(120) NULL
);
GO

IF OBJECT_ID('dbo.de_para_ean', 'U') IS NULL
CREATE TABLE dbo.de_para_ean (
    id INT IDENTITY(1,1) PRIMARY KEY,
    codigo_item NVARCHAR(120) NULL UNIQUE,
    descricao NVARCHAR(800) NULL,
    codigo_ean NVARCHAR(80) NULL
);
GO

IF OBJECT_ID('dbo.gestor_emails', 'U') IS NULL
CREATE TABLE dbo.gestor_emails (
    id INT IDENTITY(1,1) PRIMARY KEY,
    data_hora NVARCHAR(40) NOT NULL,
    remetente NVARCHAR(255) NOT NULL,
    assunto NVARCHAR(500) NOT NULL,
    conteudo_email NVARCHAR(MAX) NULL,
    acoes_tomadas NVARCHAR(MAX) NULL,
    status NVARCHAR(80) NOT NULL
);
GO

IF OBJECT_ID('dbo.historico_inventario_ciclico', 'U') IS NULL
CREATE TABLE dbo.historico_inventario_ciclico (
    id INT IDENTITY(1,1) PRIMARY KEY,
    data_contagem NVARCHAR(40) NOT NULL,
    responsavel NVARCHAR(255) NOT NULL,
    codigo_item NVARCHAR(120) NOT NULL,
    descricao_item NVARCHAR(800) NULL,
    quantidade_real INT NOT NULL,
    saldo_anterior INT NOT NULL,
    data_registro DATETIME2 NULL DEFAULT SYSDATETIME(),
    lote_peca NVARCHAR(120) NULL
);
GO

IF OBJECT_ID('dbo.templates_monitor', 'U') IS NULL
CREATE TABLE dbo.templates_monitor (
    id INT IDENTITY(1,1) PRIMARY KEY,
    nome_template NVARCHAR(255) NOT NULL,
    descricao NVARCHAR(MAX) NULL,
    ativo INT NULL DEFAULT 0
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_nf_unique' AND object_id = OBJECT_ID('dbo.entregas_efetuadas'))
CREATE UNIQUE INDEX idx_nf_unique ON dbo.entregas_efetuadas(nota_fiscal) WHERE nota_fiscal IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_faturamento_cliente' AND object_id = OBJECT_ID('dbo.faturamento'))
CREATE INDEX idx_faturamento_cliente ON dbo.faturamento(cliente);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_faturamento_emissao' AND object_id = OBJECT_ID('dbo.faturamento'))
CREATE INDEX idx_faturamento_emissao ON dbo.faturamento(emissao);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_faturamento_transportadora' AND object_id = OBJECT_ID('dbo.faturamento'))
CREATE INDEX idx_faturamento_transportadora ON dbo.faturamento(transportadora);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_items_nf' AND object_id = OBJECT_ID('dbo.faturamento_itens'))
CREATE INDEX idx_items_nf ON dbo.faturamento_itens(nf);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_cabeca_cep_unico' AND object_id = OBJECT_ID('dbo.cabeca_cep_transportadora'))
CREATE UNIQUE INDEX idx_cabeca_cep_unico
ON dbo.cabeca_cep_transportadora(prefixo_cep, municipio, uf, transportadora);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_faixa_cep_dir_unico' AND object_id = OBJECT_ID('dbo.faixa_cep_direcionamento'))
CREATE UNIQUE INDEX idx_faixa_cep_dir_unico
ON dbo.faixa_cep_direcionamento(prefixo_cep, uf, mesoregiao, transportadora);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_rotas_notas_unico' AND object_id = OBJECT_ID('dbo.rotas_predefinidas_notas'))
CREATE UNIQUE INDEX idx_rotas_notas_unico
ON dbo.rotas_predefinidas_notas(rota_id, nf);
GO
