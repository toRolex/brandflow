@echo off
chcp 65001 >nul
title Brandflow — 重启服务

echo 正在重启 Brandflow 服务...
nssm restart brandflow-control-plane
if %errorlevel% equ 0 (
    echo 服务已成功重启！
) else (
    echo 重启失败，请手动检查。
)
echo Visit: http://localhost:17890
echo.
pause
