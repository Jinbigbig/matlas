@echo off
chcp 65001 >nul
REM 移除 matlas 实时服务的开机自启项。

setlocal
set DST=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\matlas-live.cmd
if exist "%DST%" (
  del "%DST%"
  echo 已移除开机自启：%DST%
) else (
  echo 开机自启项不存在：%DST%
)
echo.
if "%~1"=="--silent" goto :done
pause

:done
endlocal
