@echo off
chcp 65001 >nul
REM 兼容旧入口：统一调用项目根目录的 start_live.bat（固定域名、幂等启动）。
call "%~dp0..\start_live.bat" %*
