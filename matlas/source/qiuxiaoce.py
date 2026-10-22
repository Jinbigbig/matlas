"""第三方对照源适配器（默认关闭）。

对照的是球小策公开开源数据集 ddzyx/qiuxiaoce-football-data，
许可为 CC BY-NC 4.0 —— 使用即须署名并保留指向源站的链接，
本站在渲染时强制带上 `REF_ATTRIBUTION`。

为什么默认关闭：
  - 引入网络依赖会破坏「离线可构建」这条底线；
  - 它每天只开放约 3 场，覆盖面不足，只能做抽样对照；
  - 对照结论不参与本站任何计算，纯展示，故非必要不启用。

启用方式：`build.py --reference`（需显式指定，构建时会打出署名行）。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

REF_NAME = "球小策开源数据集"
REF_URL = "https://github.com/ddzyx/qiuxiaoce-football-data"
REF_LICENSE = "CC BY-NC 4.0"
REF_ATTRIBUTION = f"对照数据来自 {REF_NAME}（{REF_LICENSE}）：{REF_URL}"

API_TREE = "https://api.github.com/repos/ddzyx/qiuxiaoce-football-data/git/trees/main?recursive=1"
API_BLOB = "https://api.github.com/repos/ddzyx/qiuxiaoce-football-data/git/blobs/"


class ReferenceUnavailable(RuntimeError):
    pass


def _get(url: str, timeout: int = 25) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "matlas/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_day(date_iso: str) -> dict[str, Any]:
    """拉取某日的开源对照数据。返回简化结构，失败抛 ReferenceUnavailable。

    注意：GitHub API 未鉴权时限 60 次/小时，够用但不适合高频重试。
    """
    y, m, d = date_iso.split("-")
    prefix = f"{y}/{int(m)}/{int(d)}/"
    try:
        tree = _get(API_TREE)
    except Exception as ex:  # noqa: BLE001 - 网络异常统一降级
        raise ReferenceUnavailable(f"无法获取仓库索引：{ex}") from ex

    paths = [
        t for t in tree.get("tree", [])
        if t["path"].startswith(prefix)
        and t["path"].endswith(".json")
        and "/en/" not in t["path"]
    ]
    out: dict[str, Any] = {"date": date_iso, "matches": []}
    for item in paths:
        try:
            blob = _get(API_BLOB + item["sha"])
            raw = blob.get("content", "")
            if not raw:
                continue
            import base64
            j = json.loads(base64.b64decode(raw).decode("utf-8"))
        except Exception:  # noqa: BLE001 - 单篇失败不影响整体
            continue
        res = j.get("result") or {}
        fc = j.get("forecasts") or {}
        picks = []
        for key, rename in (("scoreline", "比分"), ("goals", "进球"), ("halftime", "半全")):
            v = fc.get(key) or []
            if v:
                picks.append(f"{rename} {v[0]}")
        out["matches"].append({
            "code": (j.get("info") or {}).get("code", ""),
            "level": j.get("level", ""),
            "label": "，".join(picks),
            "result": res.get("actual_score", ""),
        })
    return out
