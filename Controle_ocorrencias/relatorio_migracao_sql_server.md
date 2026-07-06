# Relatorio de Migracao para SQL Server

Data do levantamento: 2026-07-03

## Resumo executivo

O sistema pode migrar de SQLite para Microsoft SQL Server, preferencialmente SQL Server Express no primeiro momento. A migracao e viavel, mas deve ser feita por etapas porque o codigo atual usa `sqlite3` diretamente em muitos pontos.

Banco principal atual:

- Arquivo: `sistema_operacional.db`
- Tamanho aproximado: 377 MB
- Tabelas de negocio: 26
- Pontos com conexao direta `sqlite3.connect`: 74 ocorrencias nos arquivos principais
- Arquivos mais afetados: `app.py`, `modulo_roteirizador.py`, `modulo_cep_ibge.py`

Recomendacao: nao trocar o banco de uma vez. Primeiro criar uma camada de banco, depois migrar modulo por modulo.

## Inventario das tabelas atuais

| Tabela | Registros | Observacao |
| --- | ---: | --- |
| `faturamento_itens` | 12.168 | Itens de notas fiscais. Uma das tabelas centrais. |
| `faturamento` | 6.084 | Cabecalho das notas fiscais. Tabela central para relatorios. |
| `logs_auditoria` | 286 | Auditoria operacional. |
| `canhotos_digitais` | 239 | Contem assinaturas/fotos em Base64, pode crescer muito. |
| `cep_cache` | 200 | Cache de CEP e mesorregiao. |
| `entregas_efetuadas` | 172 | Status consolidado de entregas. Possui indice unico por NF. |
| `canhotos` | 153 | Historico de canhotos. |
| `motivos_ocorrencias` | 100 | Cadastro de motivos. |
| `metas_diarias` | 61 | Metas por data. |
| `faixa_cep_direcionamento` | 16 | Regras do roteirizador. |
| `coletas` | 15 | Registros de coleta. |
| `rotas_predefinidas_criterios` | 12 | Criterios de rotas. |
| `de_para_modais` | 10 | Correcao de modal por transportadora. |
| `transportadoras` | 9 | Cadastro de transportadoras. |
| `historico_inventario_ciclico` | 7 | Historico de inventario. |
| `devolucoes` | 5 | Registros de devolucao. |
| `templates_monitor` | 5 | Templates ativos do monitor. |
| `rotas_predefinidas` | 4 | Configuracoes de rotas. |
| `configuracoes_painel` | 1 | Configuracoes gerais. |
| `ocorrencias` | 1 | Ocorrencias operacionais. |
| `usuarios_sistema` | 1 | Usuarios e senha hash. |
| `cabeca_cep_transportadora` | 0 | Configuracao de roteirizacao. |
| `de_para_ean` | 0 | De-para EAN. |
| `gestor_emails` | 0 | Gestao de emails. |
| `rotas_predefinidas_notas` | 0 | Inclusoes/exclusoes manuais em rotas. |
| `rotas_saida_dia` | 0 | Sessoes salvas do roteirizador. |

## Tabelas prioritarias para migrar primeiro

1. `usuarios_sistema`, `logs_auditoria`, `configuracoes_painel`
2. `faturamento`, `faturamento_itens`, `entregas_efetuadas`
3. `canhotos`, `canhotos_digitais`, `devolucoes`
4. `coletas`, `ocorrencias`, `motivos_ocorrencias`, `transportadoras`
5. Tabelas do roteirizador: `cep_cache`, `faixa_cep_direcionamento`, `rotas_predefinidas`, `rotas_predefinidas_criterios`, `rotas_predefinidas_notas`, `rotas_saida_dia`
6. Modulos auxiliares: `de_para_modais`, `de_para_ean`, `templates_monitor`, `historico_inventario_ciclico`

## Pontos do codigo que precisam adaptacao

### Conexao

Hoje o sistema usa:

- `sqlite3.connect(DB_FILE)`
- `get_db_connection()`
- `conn.row_factory = sqlite3.Row`
- `PRAGMA journal_mode=WAL`

No SQL Server, a conexao deve passar por `pyodbc` ou `SQLAlchemy`. A opcao mais controlada para esta base e comecar por `pyodbc`, criando uma camada unica tipo `database_adapter.py`.

### Sintaxe SQLite que precisa traducao

| SQLite atual | SQL Server |
| --- | --- |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `INT IDENTITY(1,1) PRIMARY KEY` |
| `TEXT` | `NVARCHAR(MAX)` ou `NVARCHAR(n)` |
| `REAL` | `DECIMAL(18,2)` ou `FLOAT`, conforme uso |
| `INSERT OR IGNORE` | `IF NOT EXISTS (...) INSERT ...` ou `MERGE` |
| `INSERT OR REPLACE` | `MERGE` ou `UPDATE` seguido de `INSERT` |
| `ON CONFLICT (...) DO UPDATE` | `MERGE` ou transacao com `UPDATE`/`INSERT` |
| `PRAGMA table_info` | consultas em `INFORMATION_SCHEMA.COLUMNS` |
| `PRAGMA database_list` | nao se aplica diretamente |
| `ATTACH DATABASE` | usar outro banco/schema ou tabela importada |
| `?` como placeholder | tambem funciona em `pyodbc`, mas deve ser testado query por query |

### Modulo CEP/IBGE

`modulo_cep_ibge.py` usa `ATTACH DATABASE` para anexar `database/cep_mesorregiao_brasil.db`. Esse ponto merece decisao separada:

- Caminho rapido: manter esse SQLite auxiliar por enquanto.
- Caminho definitivo: migrar tambem a base CEP/IBGE para SQL Server em schema separado, por exemplo `geo`.

Minha recomendacao: deixar CEP/IBGE em uma segunda fase para reduzir risco inicial.

## Modelo sugerido de arquitetura

Criar uma camada central:

```text
database_adapter.py
  - get_connection()
  - execute()
  - fetchone()
  - fetchall()
  - executemany()
  - transaction()
  - detect_backend()
```

Configuracao por ambiente:

```text
DB_BACKEND=sqlite
SQLSERVER_HOST=localhost
SQLSERVER_DATABASE=SistemaLogistico
SQLSERVER_TRUSTED_CONNECTION=yes
```

Durante a transicao, o sistema pode continuar usando SQLite por padrao e ativar SQL Server somente quando `DB_BACKEND=sqlserver`.

## Plano de execucao recomendado

### Fase 1 - Preparacao sem risco

- Criar backup do `sistema_operacional.db`.
- Criar `database_adapter.py`.
- Centralizar primeiro `get_db_connection()`.
- Adicionar dependencia `pyodbc` ou `SQLAlchemy`.
- Criar script `tools/inspecionar_banco.py` para repetir este levantamento.

### Fase 2 - Schema SQL Server

- Criar `database/schema_sql_server.sql`.
- Converter tipos de dados.
- Criar indices equivalentes:
  - `idx_nf_unique` em `entregas_efetuadas(nota_fiscal)`
  - `idx_faturamento_cliente`
  - `idx_faturamento_emissao`
  - `idx_faturamento_transportadora`
  - `idx_items_nf`
  - indices unicos do roteirizador

### Fase 3 - Migracao de dados

- Criar script `tools/migrar_sqlite_para_sqlserver.py`.
- Migrar tabelas em ordem, respeitando tabelas principais antes das dependentes.
- Validar contagem de registros por tabela.
- Validar amostras de dados criticos: NFs, canhotos, usuarios, entregas.

### Fase 4 - Adaptacao por modulo

Ordem recomendada:

1. Login, usuarios, configuracoes e logs.
2. Faturamento e expedicao.
3. Entregas, canhotos e devolucoes.
4. Relatorios e exportacoes.
5. Roteirizador.
6. CEP/IBGE.

### Fase 5 - Teste paralelo

- Rodar uma copia do sistema apontando para SQL Server.
- Comparar telas principais com o sistema SQLite.
- Testar importacao manual de planilhas.
- Testar baixa de entrega, canhotos, devolucoes e relatorios.
- Somente depois promover SQL Server como banco oficial.

## Riscos principais

- Muitas consultas estao espalhadas pelo `app.py`, entao uma troca direta aumenta risco de regressao.
- Campos numericos importantes hoje estao como texto, exemplo `valor_total_nf`, `peso_bruto_nf`, `qtde`. SQL Server permite melhorar isso, mas converter tudo de uma vez pode alterar comportamento.
- `canhotos_digitais.assinatura_base64` e `devolucoes.imagem_base64` podem deixar o banco pesado. Em SQL Server, talvez seja melhor guardar arquivos em pasta e salvar apenas caminho/metadata.
- O modulo CEP/IBGE depende de SQLite auxiliar anexado, o que nao existe da mesma forma no SQL Server.
- Alguns `ALTER TABLE` sao executados em tempo de uso. Em SQL Server, isso deve virar migracao controlada.

## Proxima acao recomendada

Criar a camada `database_adapter.py` mantendo SQLite como padrao. Esse passo prepara a migracao sem mudar o comportamento atual do sistema.

Depois disso, criar o schema SQL Server e um script de migracao para ambiente de teste.

## Andamento

- 2026-07-03: criada a camada `database_adapter.py`.
- 2026-07-03: `get_db_connection()` passou a usar o adaptador central, mantendo SQLite como padrao.
- 2026-07-03: adicionada dependencia opcional `pyodbc` para preparar conexao SQL Server.
- 2026-07-03: criado schema inicial `database/schema_sql_server.sql`.
- 2026-07-03: criado script inicial `tools/migrar_sqlite_para_sqlserver.py`, em modo diagnostico por padrao.
- 2026-07-03: SQL Server 2025 local conectado em `localhost`, banco `SistemaLogistico`.
- 2026-07-03: migracao executada com sucesso para SQL Server.
- 2026-07-03: validacao de contagens concluida com 26/26 tabelas batendo entre SQLite e SQL Server.
- 2026-07-03: criado script `tools/validar_migracao_sqlserver.py`.
- 2026-07-03: app importou em modo SQL Server; login `admin` validado via smoke test.
- 2026-07-03: criados `tools/testar_app_sqlserver.py` e `iniciar_sqlserver_teste.bat`.
- 2026-07-03: adaptador passou a devolver linhas SQL Server com acesso por nome, compatível com `sqlite3.Row`.
- 2026-07-03: inicializadores SQLite foram desativados em modo SQL Server.
- 2026-07-03: fluxos validados em SQL Server: login, contagem de faturamento, motivos, metas, canhotos, missão e listagem de usuários.
- 2026-07-03: conexões diretas `sqlite3.connect(DB_FILE)` restantes no `app.py`: 48.

Configuracao futura para teste SQL Server:

```text
DB_BACKEND=sqlserver
SQLSERVER_HOST=localhost\SQLEXPRESS
SQLSERVER_DATABASE=SistemaLogistico
SQLSERVER_TRUSTED_CONNECTION=yes
SQLSERVER_TRUST_CERT=yes
```

## Status atual - 2026-07-03

- Rotas principais adaptadas para SQL Server: relatorio de faturamento, relatorio local, dashboard de expedicao, transportadoras, devolucoes, canhotos, EAN, gestor de e-mails, curva ABC e inventario ciclico.
- Conexoes diretas `sqlite3.connect(DB_FILE)` restantes no `app.py`: 1, apenas na inicializacao SQLite de inventario, protegida para nao executar quando `DB_BACKEND=sqlserver`.
- Smoke tests SQL Server aprovados: login admin, faturamento, relatorios, dashboard, EAN, devolucoes, transportadoras, emails e inventario.
- Validacao de migracao: tabelas operacionais batendo. `logs_auditoria` pode divergir porque os testes de login gravam novas entradas no SQL Server.

Configuracao validada localmente:

```text
DB_BACKEND=sqlserver
SQLSERVER_HOST=localhost
SQLSERVER_DATABASE=SistemaLogistico
SQLSERVER_TRUSTED_CONNECTION=yes
SQLSERVER_TRUST_CERT=yes
```
