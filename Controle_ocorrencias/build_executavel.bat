@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo  Build — Sistema Logistico Integrado (.exe para rede)
echo ============================================================
echo.

cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale Python 3.10+ e tente novamente.
    pause
    exit /b 1
)

echo [1/3] Instalando dependencias...
py -3 -m pip install --upgrade pip >nul
py -3 -m pip install flask pywebview pandas openpyxl pyinstaller requests pyodbc >nul
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)

echo [2/3] Gerando executavel com PyInstaller...
py -3 -m PyInstaller app.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERRO] PyInstaller falhou. Verifique o log acima.
    pause
    exit /b 1
)

echo [3/3] Copiando arquivos auxiliares para dist\...
if not exist "dist\ dados" mkdir "dist\dados" 2>nul

if exist "sistema_operacional.db" copy /Y "sistema_operacional.db" "dist\" >nul
if exist "MODAIS.csv" copy /Y "MODAIS.csv" "dist\" >nul
if not exist "dist\database" mkdir "dist\database" >nul
if exist "database\cep_mesorregiao_brasil.db" copy /Y "database\cep_mesorregiao_brasil.db" "dist\database\" >nul
copy /Y "liberar_porta_firewall.bat" "dist\" >nul
copy /Y "remover_porta_firewall.bat" "dist\" >nul

(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%%~dp0"
echo echo Servidor logístico — modo rede ^(sem janela desktop^)
echo SistemaLogistico.exe --servidor
echo pause
) > "dist\iniciar_servidor_rede.bat"

echo.
echo ============================================================
echo  CONCLUIDO
echo  Executavel: dist\SistemaLogistico.exe
echo.
echo  Uso na maquina servidor:
echo    - Duplo clique: abre janela + servidor na rede (porta 5000)
echo    - Somente rede: SistemaLogistico.exe --servidor
echo    - Outra porta:  SistemaLogistico.exe --porta 8080
echo.
echo  Outros PCs: http://IP_DO_SERVIDOR:5000/
echo.
echo  Antes de usar na rede, execute (como Admin):
echo    liberar_porta_firewall.bat
echo ============================================================
echo.
pause
