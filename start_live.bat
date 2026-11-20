@echo off
chcp 65001 >nul
REM matlas 本地实时服务一键启动：同时拉起数据服务 + cloudflared 隧道
REM 前端配置见 LIVE_API_BASE（config.js）。Quick Tunnel 每次启动域名不同，
REM 启动后从 live_url.txt 读取本次公网域名。

setlocal
cd /d "%~dp0"

set PY=C:\Users\Jin\.workbuddy\binaries\python\versions\3.13.12\python.exe
if not exist "%PY%" set PY=python
set CF=%~dp0tools\cloudflared.exe
if not exist "%CF%" set CF=C:\Program Files (x86)\cloudflared\cloudflared.exe
if not exist "%CF%" set CF=C:\Program Files\cloudflared\cloudflared.exe

echo [1/2] 启动本地数据服务 127.0.0.1:8787 ...
start "matlas-live-server" /min "%PY%" live_server.py --port 8787

echo [2/2] 建立公网隧道，等待域名 ...
if exist live_url.txt del live_url.txt
(
  "%CF%" tunnel --no-autoupdate --url http://127.0.0.1:8787 2>&1 | findstr /R "trycloudflare.com"
) > live_url.txt

echo.
echo 本次公网域名：
type live_url.txt
echo.
echo 服务已运行。关闭两个窗口（matlas-live-server 与 cloudflared）即停止。
endlocal
