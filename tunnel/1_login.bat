@echo off
chcp 65001 >nul
REM 第一步：授权 Cloudflare 账号（只需一次）。会打开浏览器让你登录并选域名。
REM 授权成功后凭证存到 %USERPROFILE%\.cloudflared\，后续启动不再需要登录。

set CF=C:\Program Files (x86)\cloudflared\cloudflared.exe
if not exist "%CF%" set CF=C:\Program Files\cloudflared\cloudflared.exe

echo 正在打开 Cloudflare 授权页面，请在浏览器中登录并授权你的域名...
echo 授权完成后回到这里继续。
echo.
"%CF%" tunnel login
pause
