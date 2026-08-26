@echo off
REM ---------------------------------------------------------------------------
REM Refresh diario do JEM Marketing Daily Report: Magento + ClickUp, ambos ao vivo.
REM Agendado para 22:00 local (UTC-3) = 18:00 Phoenix -- fim do dia de trabalho, para
REM que as setas de tendencia cubram o dia INTEIRO (elas comparam o fechamento de
REM ontem com o momento desta execucao).
REM
REM Tudo vai para refresh.log, incluindo os avisos de sanidade do build_data.py
REM (status fora do mapa, tarefas sem historico, all_new_suspicious). Job sem log e
REM job que falha calado -- confira este arquivo se o dashboard parecer parado.
REM ---------------------------------------------------------------------------
setlocal

set "DIR=%~dp0"
set "PY=C:\Users\MaynaraAmaral\anaconda3\python.exe"
set "LOG=%DIR%refresh.log"

REM Obrigatorio: build_data.py imprime acentos, e o console/arquivo em cp1252
REM estoura UnicodeEncodeError e MATA o script no meio. Ja aconteceu com o probe.
set "PYTHONIOENCODING=utf-8"

echo.>> "%LOG%"
echo ============================================================>> "%LOG%"
echo [%date% %time%] iniciando refresh>> "%LOG%"

if not exist "%PY%" (
    echo [%date% %time%] ERRO: interpretador nao encontrado em %PY%>> "%LOG%"
    echo    ^(python puro nesta maquina e o stub da Microsoft Store, ver CLAUDE.md secao 5^)>> "%LOG%"
    endlocal
    exit /b 9
)

"%PY%" "%DIR%build_data.py">> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo [%date% %time%] FALHOU com codigo %RC%>> "%LOG%"
) else (
    echo [%date% %time%] concluido OK>> "%LOG%"
)

endlocal & exit /b %RC%
