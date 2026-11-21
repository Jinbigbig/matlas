@echo off
chcp 65001 >nul
REM matlas 实时服务统一入口：本地数据服务 + Cloudflare Named Tunnel（固定域名 www.matlas.top）
REM 重复双击不会产生第二个进程；--silent 由开机自启调用，不暂停窗口。

setlocal
cd /d "%~dp0"
set ROOT=%CD%

set PY=C:\Users\Jin\.workbuddy\binaries\python\versions\3.13.12\python.exe
if not exist "%PY%" set PY=python
set CF=%ROOT%\tools\cloudflared.exe
if not exist "%CF%" set CF=C:\Program Files (x86)\cloudflared\cloudflared.exe
if not exist "%CF%" set CF=C:\Program Files\cloudflared\cloudflared.exe

echo [1/3] 本地数据服务 127.0.0.1:8787
netstat -ano | findstr ":8787" | findstr "LISTENING" >nul
if errorlevel 1 (
  start "matlas-live-server" /min "%PY%" "%ROOT%\live_server.py" --port 8787
  echo    已启动
) else (
  echo    已在运行，跳过
)

echo [2/3] Cloudflare 隧道 matlas-live
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cloudflared.exe' -and $_.CommandLine -match 'matlas-live' }; if ($p) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  if not exist "%CF%" (
    echo    未找到 cloudflared.exe
  ) else (
    start "matlas-cloudflared" /min "%CF%" tunnel --config "%ROOT%\tunnel\config.yml" --no-autoupdate run matlas-live
    echo    已启动
  )
) else (
  echo    已在运行，跳过
)

echo [3/3] 健康检查
powershell -NoProfile -Command "Start-Sleep -Seconds 2; try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/health' -TimeoutSec 3; Write-Host ('   本地服务 ok，天数 ' + $r.dates) } catch { Write-Host '   本地服务尚未就绪' }"

echo.
echo 接口地址：https://www.matlas.top/api/live?date=YYYY-MM-DD
echo 域名检查：https://www.matlas.top/api/health
echo.

if "%~1"=="--silent" goto :done
pause

:done
endlocal
