@echo off
chcp 65001 >nul 2>&1
color 0A
cls

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║     CONTROLE DE OFICINA MECÂNICA — Gerador de Executável      ║
echo  ║     Este script instala as dependências e gera o .exe        ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Verifica se Python está instalado ────────────────────────────────
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo  [ERRO] Python nao encontrado no PATH.
    echo.
    echo  Por favor instale o Python 3.8 ou superior em:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANTE: Marque a opcao "Add Python to PATH" durante a instalacao!
    echo.
    pause
    exit /b 1
)

FOR /F "tokens=2 delims= " %%V IN ('python --version 2^>^&1') DO SET PY_VER=%%V
echo  [OK] Python %PY_VER% encontrado.
echo.

REM ── Verifica versão mínima (3.7) ─────────────────────────────────────
python -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
IF ERRORLEVEL 1 (
    echo  [ERRO] Python %PY_VER% muito antigo. Necessario 3.7 ou superior.
    echo  Baixe a versao mais recente em: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ── Pasta de trabalho = onde este .bat está ───────────────────────────
cd /d "%~dp0"
echo  [INFO] Pasta de trabalho: %CD%
echo.

REM ── Verifica se o arquivo principal existe ────────────────────────────
IF NOT EXIST "sistema_oficina_v2.py" (
    echo  [ERRO] Arquivo sistema_oficina_v2.py nao encontrado nesta pasta.
    echo  Coloque este .bat na mesma pasta que o sistema_oficina_v2.py
    pause
    exit /b 1
)
echo  [OK] Arquivo sistema_oficina_v2.py encontrado.
echo.

REM ── Atualiza pip ──────────────────────────────────────────────────────
echo  [1/5] Atualizando pip...
python -m pip install --upgrade pip --quiet
echo  [OK] pip atualizado.
echo.

REM ── Instala PyInstaller ───────────────────────────────────────────────
echo  [2/5] Instalando PyInstaller...
python -m pip install pyinstaller --upgrade --quiet
IF ERRORLEVEL 1 (
    echo  [ERRO] Falha ao instalar PyInstaller. Verifique sua conexao.
    pause
    exit /b 1
)
echo  [OK] PyInstaller instalado.
echo.

REM ── Instala reportlab ─────────────────────────────────────────────────
echo  [3/5] Instalando reportlab (geracao de PDF)...
python -m pip install reportlab --upgrade --quiet
echo  [OK] reportlab instalado.
echo.

REM ── Instala Pillow ────────────────────────────────────────────────────
echo  [4/5] Instalando Pillow (logos de marcas)...
python -m pip install Pillow --upgrade --quiet
echo  [OK] Pillow instalado.
echo.

echo  Instalando pyodbc (SQL Server)...
python -m pip install pyodbc --upgrade --quiet
echo  [OK] pyodbc instalado.
echo.

REM ── Cria pasta de logos se não existir ───────────────────────────────
IF NOT EXIST "logos_marcas" mkdir logos_marcas
echo  [OK] Pasta logos_marcas pronta.
echo.

REM ── Remove build anterior se existir ─────────────────────────────────
echo  [5/5] Preparando ambiente de build...
IF EXIST "dist\ControleOficina.exe" (
    echo  [INFO] Removendo versao anterior...
    del /q "dist\ControleOficina.exe" >nul 2>&1
)
IF EXIST "build" (
    rmdir /s /q "build" >nul 2>&1
)
echo  [OK] Ambiente limpo.
echo.

REM ── Executa PyInstaller ───────────────────────────────────────────────
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║  Gerando o executavel... isso pode levar 1 a 3 minutos.     ║
echo  ║  Nao feche esta janela!                                      ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

pyinstaller ControleOficina.spec --noconfirm --clean

IF ERRORLEVEL 1 (
    echo.
    echo  ╔══════════════════════════════════════════════════════════════╗
    echo  ║  [ERRO] Falha ao gerar o executavel.                        ║
    echo  ║  Verifique os erros acima e tente novamente.                ║
    echo  ╚══════════════════════════════════════════════════════════════╝
    pause
    exit /b 1
)

REM ── Verifica se o exe foi gerado ──────────────────────────────────────
IF NOT EXIST "dist\ControleOficina.exe" (
    echo.
    echo  [ERRO] Executavel nao encontrado em dist\ControleOficina.exe
    echo  Verifique os logs acima.
    pause
    exit /b 1
)

REM ── Copia arquivos necessários para dist\ ────────────────────────────
echo.
echo  Copiando arquivos adicionais para a pasta dist\...

REM Copia logos se existirem
IF EXIST "logos_marcas" (
    xcopy "logos_marcas" "dist\logos_marcas\" /E /I /Q >nul 2>&1
    echo  [OK] Pasta logos_marcas copiada.
)

REM ── Obtém tamanho do exe ──────────────────────────────────────────────
FOR %%F IN ("dist\ControleOficina.exe") DO SET EXE_SIZE=%%~zF
SET /A EXE_MB=%EXE_SIZE% / 1048576

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                                                              ║
echo  ║  [SUCESSO] Executavel gerado com sucesso!                   ║
echo  ║                                                              ║
echo  ║  Arquivo: dist\ControleOficina.exe                          ║
echo  ║  Tamanho: ~%EXE_MB% MB                                          ║
echo  ║                                                              ║
echo  ║  Para distribuir:                                            ║
echo  ║  1. Copie a pasta  dist\  para um pendrive ou envie         ║
echo  ║  2. O destinatario clica duas vezes em ControleOficina.exe  ║
echo  ║  3. Nao e necessario instalar Python na maquina destino     ║
echo  ║                                                              ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

REM ── Abre a pasta dist\ no Explorer ───────────────────────────────────
echo  Abrindo a pasta com o executavel...
start "" explorer.exe "%~dp0dist"

pause
