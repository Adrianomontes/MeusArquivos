@echo off
chcp 65001 >nul
setlocal

:: Remove a regra de firewall criada por liberar_porta_firewall.bat

set "PORTA=5000"
if not "%~1"=="" set "PORTA=%~1"

set "NOME_REGRA=Sistema Logistico - TCP %PORTA%"

net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '%PORTA%' -Verb RunAs"
    exit /b
)

echo Removendo regra: %NOME_REGRA%
netsh advfirewall firewall delete rule name="%NOME_REGRA%"
netsh advfirewall firewall delete rule name="Sistema Logistico - Executavel"

echo Concluido.
pause
