@echo off
chcp 65001 >nul
REM matlas 实时服务停止脚本：只结束本项目的 python live_server.py 与 cloudflared matlas-live 进程。

setlocal
echo 停止 matlas 实时服务 ...
powershell -NoProfile -Command "$ps = Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'live_server.py') -or ($_.Name -eq 'cloudflared.exe' -and $_.CommandLine -match 'matlas-live') }; foreach ($p in $ps) { Stop-Process -Id $p.ProcessId -Force; Write-Host ('   已停止 PID ' + $p.ProcessId + ' ' + $p.Name) }; if (-not $ps) { Write-Host '   未发现运行中的服务' }"
echo.
if "%~1"=="--silent" goto :done
pause

:done
endlocal
