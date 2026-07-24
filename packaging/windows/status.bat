@echo off
chcp 65001 >nul
title Brandflow — 查看状态

echo Brandflow 服务状态：
nssm status brandflow-control-plane
sc query brandflow-control-plane 2>&1 | findstr STATE
echo.
echo 进程:
tasklist /FI "IMAGENAME eq python.exe" /V /FO LIST 2>nul
echo.
pause
