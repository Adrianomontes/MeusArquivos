@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

set DB_BACKEND=sqlserver
set SQLSERVER_HOST=localhost
set SQLSERVER_DATABASE=SistemaLogistico
set SQLSERVER_TRUSTED_CONNECTION=yes
set SQLSERVER_TRUST_CERT=yes

echo Iniciando Sistema Logistico em modo TESTE com SQL Server...
echo Banco: %SQLSERVER_HOST%\%SQLSERVER_DATABASE%
echo.

py -3 app.py --servidor

pause
