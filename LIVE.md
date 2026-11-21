# Matlas 实时数据服务

## 链路

```
www.matlas.top → Cloudflare Tunnel matlas-live → 127.0.0.1:8787 (live_server.py) → jinbet / matlas 数据
```

前端单场页运行时请求接口，替换比分与赔率趋势；请求失败时保留构建期静态内容。

## 文件

| 文件 | 用途 |
| --- | --- |
| `live_server.py` | 零依赖 HTTP 服务与静态导出 |
| `start_live.bat` | 一键启动：本地服务 + 固定域名隧道，重复执行不重复起进程 |
| `stop_live.bat` | 停止本项目的本地服务与隧道进程 |
| `install_autostart.bat` | 安装登录后自启 |
| `uninstall_autostart.bat` | 移除自启项 |
| `tunnel/config.yml` | 隧道 ID、凭证路径、域名 `www.matlas.top` |
| `tunnel/1_login.bat` | Cloudflare 账号授权 |
| `tunnel/2_create_tunnel.bat` | 创建隧道与 DNS 路由 |

## 启动与自启

| 操作 | 文件 / 命令 |
| --- | --- |
| 启动 | 双击 `start_live.bat` |
| 停止 | 双击 `stop_live.bat` |
| 安装自启 | 双击 `install_autostart.bat` |
| 移除自启 | 双击 `uninstall_autostart.bat` |
| 单独启动服务 | `python live_server.py --port 8787` |
| 静态导出 | `python live_server.py --export` |

自启项位置：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\matlas-live.cmd`，登录后调用 `start_live.bat --silent`。

## 接口

| 路径 | 返回 |
| --- | --- |
| `/api/health` | 服务状态、当前时间、可用天数 |
| `/api/live?date=YYYY-MM-DD` | 当日全部场次的比分、状态、盘口、赔率趋势 SVG |
| `/api/live/<match_id>` | 单场数据 |
| `/api/dates` | 可用日期列表 |

本地地址 `http://127.0.0.1:8787`，公网地址 `https://www.matlas.top`。

## 依赖位置

| 依赖 | 路径 |
| --- | --- |
| Python | `C:\Users\Jin\.workbuddy\binaries\python\versions\3.13.12\python.exe`（缺失时用 PATH 中的 python） |
| cloudflared | `<项目>\tools\cloudflared.exe`、`C:\Program Files (x86)\cloudflared\cloudflared.exe`、`C:\Program Files\cloudflared\cloudflared.exe` 依次查找 |
| 隧道凭证 | `%USERPROFILE%\.cloudflared\518c10e0-4bac-4ecf-bdb8-a882edb321c3.json` |
| 数据源 | `C:\Users\Jin\jinbet\odds_ticks.json`、`results_data.json`、`fixtures.json` |
| 场次骨架 | `<项目>\data\days\*.json` |

## 静态后门

`python live_server.py --export` 生成 `data/live/<日期>.json` 与 `index.json`。切换时把 `matlas/render/layout.py` 的 `window.LIVE_API_BASE` 改为静态 JSON 所在地址，其余逻辑不变。`data/live/` 不进仓库。

## 云端备份

以上脚本、配置与文档均提交在 `main` 分支的 `C:\Users\Jin\matlas`。
