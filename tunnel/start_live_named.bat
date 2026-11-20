@echo off
chcp 65001 >nul
REM Named Tunnel 正式启动脚本：固定域名，前端 fetch 地址可写死。
REM 前置：已完成 1_login.bat 授权 + 2_create_tunnel.bat 建隧道 + 填好 config.yml

setlocal
cd /d "%~dp0"

set PY=C:\Users\Jin\.workbuddy\binaries\python\versions\3.13.12\python.exe
if not exist "%PY%" set PY=python
set CF=C:\Program Files (x86)\cloudflared\cloudflared.exe
if not exist "%CF%" set CF=C:\Program Files\cloudflared\cloudflared.exe

echo [1/2] 启动本地数据服务 127.0.0.1:8787 ...
start "matlas-live-server" /min "%PY%" "..\live_server.py" --port 8787

echo [2/2] 启动固定域名隧道 ...
start "matlas-cloudflared" /min "%CF%" tunnel --config config.yml run matlas-live

echo.
echo 服务与隧道已启动。固定域名见 config.yml 的 hostname。
echo 关闭两个 min 窗口即停止。
endlocal
