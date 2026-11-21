"""方案 A 初始化：用 CF API Token 创建 KV namespace 并写入 .env。

前置：.env 里填好 CF_ACCOUNT_ID / CF_API_TOKEN。
    API Token 权限需含：Account > Workers KV Storage > Edit。

用法：python cf_bootstrap.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
CF_API = "https://api.cloudflare.com/client/v4"


def load_env() -> dict[str, str]:
    d = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def set_env(key: str, value: str) -> None:
    """写入/更新 .env 的一个键，保留其他内容与注释。"""
    lines = ENV.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def api(path: str, token: str, method: str = "GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        CF_API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    env = load_env()
    account = env.get("CF_ACCOUNT_ID", "").strip()
    token = env.get("CF_API_TOKEN", "").strip()
    if not account or not token:
        print("[!] 请先在 .env 填 CF_ACCOUNT_ID / CF_API_TOKEN")
        return 1

    # 校验 token
    try:
        me = api("/user/tokens/verify", token)
        if not me.get("success"):
            print("[!] API Token 无效：", me.get("errors"))
            return 1
        print(f"[ok] Token 有效：{me['result']['status']}")
    except Exception as ex:  # noqa: BLE001
        print(f"[!] 无法连接 CF API：{ex}")
        return 1

    # 建 KV（同名复用）
    try:
        ns_list = api(f"/accounts/{account}/storage/kv/namespaces", token)
        existing = next((n for n in ns_list.get("result", []) if n["title"] == "MATLAS_KV"), None)
        if existing:
            ns_id = existing["id"]
            print(f"[ok] 复用已有 KV namespace: {ns_id}")
        else:
            created = api(f"/accounts/{account}/storage/kv/namespaces", token, "POST", {"title": "MATLAS_KV"})
            ns_id = created["result"]["id"]
            print(f"[ok] 新建 KV namespace: {ns_id}")
    except Exception as ex:  # noqa: BLE001
        print(f"[!] 创建 KV 失败：{ex}")
        return 1

    set_env("CF_KV_NAMESPACE_ID", ns_id)

    # 从模板生成 wrangler.toml（含真实 id），该文件不进仓库
    tpl = ROOT / "wrangler.toml.example"
    wt = ROOT / "wrangler.toml"
    if tpl.exists():
        txt = tpl.read_text(encoding="utf-8")
        txt = re.sub(r'id = "REPLACE_WITH_CF_KV_NAMESPACE_ID"', f'id = "{ns_id}"', txt)
        wt.write_text(txt, encoding="utf-8")
        print(f"[ok] 已生成 wrangler.toml: id={ns_id}")

    print(f"[ok] 已写入 .env: CF_KV_NAMESPACE_ID={ns_id}")
    print("[→] 下一步运行 cf_setup.bat 部署静态站 + Functions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
