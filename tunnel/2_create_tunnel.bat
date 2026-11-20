@echo off
chcp 65001 >nul
REM 第二步：创建 Named Tunnel 并绑定固定域名。
REM 用法：2_create_tunnel.bat 你的子域名
REM 例：  2_create_tunnel.bat live     -> 生成 live.你的域名

setlocal
cd /d "%~dp0"

set CF=C:\Program Files (x86)\cloudflared\cloudflared.exe
if not exist "%CF%" set CF=C:\Program Files\cloudflared\cloudflared.exe

set SUB=%1
if "%SUB%"=="" (
  echo 用法：2_create_tunnel.bat 子域名
  echo 例：  2_create_tunnel.bat live
  exit /b 1
)

echo [1/3] 创建隧道 matlas-live ...
"%CF%" tunnel create matlas-live
if errorlevel 1 (
  echo 隧道已存在或创建失败，继续尝试获取 ID...
)

echo [2/3] 读取隧道 ID ...
for /f "tokens=2 delims=[]" %%i in ('"%CF%" tunnel list ^| findstr matlas-live') do set TID=%%i
if "%TID%"=="" (
  echo 未能读取隧道 ID，请手动运行 cloudflared tunnel list 确认。
  pause
  exit /b 1
)
echo 隧道 ID: %TID%

echo [3/3] 配置 DNS 路由 %SUB%.你的域名 ...
"%CF%" tunnel route dns matlas-live %SUB%

echo.
echo 配置完成。请把下面的隧道 ID 填到 config.yml 的 tunnel 字段：
echo   %TID%
echo 并把 LIVE_API_BASE 设为 https://%SUB%.你的域名
pause
endlocal
