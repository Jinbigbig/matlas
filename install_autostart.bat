@echo off
chcp 65001 >nul
REM 安装开机自启：在 Windows 启动文件夹生成 matlas-live.cmd，登录后调用项目根目录的 start_live.bat --silent。

setlocal
set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%
set DST=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\matlas-live.cmd

> "%DST%" echo @echo off
>> "%DST%" echo start "" /min "%ROOT%\start_live.bat" --silent

echo 已安装开机自启：%DST%
echo.
type "%DST%"
echo.
if "%~1"=="--silent" goto :done
pause

:done
endlocal
