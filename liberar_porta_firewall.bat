@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
::  Libera porta TCP no Firewall do Windows (acesso na rede)
::  Uso: liberar_porta_firewall.bat          (porta 5000)
::       liberar_porta_firewall.bat 8080     (outra porta)
::  Execute na MAQUINA SERVIDOR, como Administrador.
:: ============================================================

set "PORTA=5000"
if not "%~1"=="" set "PORTA=%~1"

set "NOME_REGRA=Sistema Logistico - TCP %PORTA%"

:: Reabrir como administrador se necessario
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo Permissao de administrador necessaria para alterar o firewall.
    echo Solicitando elevacao...
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '%PORTA%' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo.
echo ============================================================
echo  Firewall Windows — liberar porta %PORTA% (TCP entrada)
echo ============================================================
echo.

:: Remove regra antiga com o mesmo nome (evita duplicata)
netsh advfirewall firewall delete rule name="%NOME_REGRA%" >nul 2>&1

:: Cria regra para rede local e publica (perfis Domain, Private, Public)
netsh advfirewall firewall add rule ^
    name="%NOME_REGRA%" ^
    dir=in ^
    action=allow ^
    protocol=TCP ^
    localport=%PORTA% ^
    profile=any ^
    enable=yes ^
    description="Permite acesso ao Sistema Logistico Integrado na porta %PORTA%"

if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar a regra de firewall.
    pause
    exit /b 1
)

:: Regra extra para o executavel (se existir na pasta)
if exist "%~dp0SistemaLogistico.exe" (
    set "NOME_EXE=Sistema Logistico - Executavel"
    netsh advfirewall firewall delete rule name="!NOME_EXE!" >nul 2>&1
    netsh advfirewall firewall add rule ^
        name="!NOME_EXE!" ^
        dir=in ^
        action=allow ^
        program="%~dp0SistemaLogistico.exe" ^
        profile=any ^
        enable=yes ^
        description="Permite o Sistema Logistico Integrado receber conexoes"
)

echo [OK] Regra criada: %NOME_REGRA%
echo      Protocolo: TCP  |  Porta: %PORTA%  |  Direcao: Entrada  |  Acao: Permitir
echo.

:: Mostrar IPs locais para os outros PCs
echo Enderecos para acesso na rede (use em outro PC no navegador):
echo.

set "TEM_IP=0"
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i /c:"IPv4"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
    if not "!IP!"=="" (
        if not "!IP:~0,7!"=="169.254" (
            echo   http://!IP!:%PORTA%/
            set "TEM_IP=1"
        )
    )
)

if "!TEM_IP!"=="0" (
    echo   (Nenhum IPv4 detectado — verifique ipconfig manualmente)
)

echo.
echo   Local nesta maquina: http://127.0.0.1:%PORTA%/
echo.
echo ============================================================
echo  Pronto. Inicie o sistema e teste de outro PC na mesma rede.
echo ============================================================
echo.
pause
