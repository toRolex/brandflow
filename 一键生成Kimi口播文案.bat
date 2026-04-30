@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PRODUCT=%*"
if "%PRODUCT%"=="" (
  set /p "PRODUCT=请输入菌菇/品名（默认：见手青）："
)
if "%PRODUCT%"=="" set "PRODUCT=见手青"

py -3.11 "%~dp0kimi_two_stage_script.py" "%PRODUCT%"
pause
