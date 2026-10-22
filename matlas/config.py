"""站点级配置。

所有对外身份、路径与开关集中在此，避免散落到渲染层。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# 线上地址集中在这里，避免散落到 argv 与渲染层后出现两套域名。
#
# 必须是「无需任何前置参数即可打开」的公开地址 —— canonical / sitemap / llms.txt
# 里的 URL 会被搜索引擎与 AI 爬虫直接抓取，带 sharecode 才有权限的地址等于 403。
# 现用 GitHub Pages（gh-pages 分支，允许子路径 /matlas/）。
# 内置通道 https://matlas.app.workbuddy.host 需带 ?sharecode=... 才能访问，
# 仅作人工预览镜像，不可作为 canonical。
DEFAULT_BASE_URL = "https://jinbigbig.github.io/matlas"


@dataclass(frozen=True)
class Config:
    site_root: Path
    out_dir: Path
    data_dir: Path
    static_dir: Path | None = None

    # ---- 站点身份（改成你自己的域名即可）----
    site_name: str = "Matlas"
    site_tagline: str = "足球赛事量化图谱"
    site_desc: str = (
        "Matlas 逐场公开足球赛事的结构化量化数据与推演结论，"
        "赛前固化、赛后回填，全部历史可核验、可复算。"
    )
    base_url: str = DEFAULT_BASE_URL
    author: str = "Matlas"
    language: str = "zh-CN"

    # ---- 免责：站点定位为数据分析，不做任何投注建议 ----
    disclaimer: str = (
        "本站内容为体育赛事数据分析与技术交流参考，不构成任何投注建议。"
    )

    # ---- 对照源开关：默认全关，不联网也能构建 ----
    enable_reference_source: bool = False

    # ---- 每页列表上限 ----
    archive_page_size: int = 40

    @property
    def days_dir(self) -> Path:
        return self.data_dir / "days"

    @property
    def out_days_dir(self) -> Path:
        return self.out_dir / "days"

    @property
    def out_matches_dir(self) -> Path:
        return self.out_dir / "matches"

    def ensure_dirs(self) -> None:
        for p in (
            self.out_dir,
            self.out_days_dir,
            self.out_matches_dir,
            self.days_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = Config(
    site_root=Path(__file__).resolve().parent.parent,
    out_dir=Path(__file__).resolve().parent.parent / "_site",
    data_dir=Path(__file__).resolve().parent.parent / "data",
)
