@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Build TRIAL — Sistema Logistico (envio a clientes)
echo ============================================================
echo.

set EDICAO_TRIAL=1

py -3 -m PyInstaller app_trial.spec --noconfirm
if errorlevel 1 (
    echo [ERRO] Build trial falhou.
    pause
    exit /b 1
)

echo Criando banco demonstrativo trial...
py -3 scripts\criar_banco_trial.py
if errorlevel 1 (
    echo [ERRO] Falha ao criar sistema_trial.db
    pause
    exit /b 1
)

if exist "sistema_trial.db" copy /Y "sistema_trial.db" "dist\" >nul
if exist "MODAIS.csv" copy /Y "MODAIS.csv" "dist\" >nul
if not exist "dist\database" mkdir "dist\database" >nul
if exist "database\cep_mesorregiao_brasil.db" copy /Y "database\cep_mesorregiao_brasil.db" "dist\database\" >nul

echo.
echo ============================================================
echo  Build TRIAL concluido: dist\SistemaLogisticoTrial.exe
echo.
echo  Para montar ZIP de envio ao cliente:
echo    py -3 scripts\montar_pacote_trial.py --email cliente@empresa.com --empresa "Nome" --dias 15
echo ============================================================
pause
