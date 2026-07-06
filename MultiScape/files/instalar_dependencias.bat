@echo off
chcp 65001 >nul 2>&1
color 0B
cls

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║   MULTI ESCAPE ERP — Instalador de Dependências             ║
echo  ║   (Apenas instalação dos pacotes Python necessários)        ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.
echo  Este script instala apenas os pacotes Python (nao gera o .exe)
echo  Use-o se quiser rodar o sistema diretamente pelo Python.
echo.

python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo  [ERRO] Python nao encontrado.
    echo  Instale em: https://www.python.org/downloads/
    pause
    exit /b 1
)

FOR /F "tokens=2 delims= " %%V IN ('python --version 2^>^&1') DO SET PY_VER=%%V
echo  Python %PY_VER% encontrado. Instalando dependencias...
echo.

echo  Instalando reportlab (PDF)...
python -m pip install reportlab --quiet
echo  Instalando Pillow (imagens/logos)...
python -m pip install Pillow --quiet
echo  Instalando pyodbc (SQL Server)...
python -m pip install pyodbc --quiet

echo.
echo  Concluido! Para rodar o sistema:
echo  python sistema_oficina_v2.py
echo.
pause
