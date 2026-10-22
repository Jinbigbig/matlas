"""构建期红线自检。

RULES.md 里写的规则不能只靠自觉 —— 这个文件把 §3.1～§3.4 变成可执行检查，
每次 build 结束自动扫描 `_site/` 下所有 HTML，命中即报出文件名与行号。

规则来源：jinbet 长期约定（见 RULES.md「继承的规则」），两边必须逐条一致。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# ---- §3.1 公开页文案红线 ----

INTERNAL_TERMS = [
    "目标函数", "口径一致性", "偏差归因", "probe", "χ²", "chi-square",
    "Brier", "argmax", "McNemar", "Platt", "Kalman", "贝叶斯",
    " Sidd ", " isotonic ", "温度缩放",
]

REASONING_TRACE = [
    "λ=", "λ×", "lambda=", "校准后", "零封修正", "乘法因子",
    "泊松", "Poisson", "蒙特卡洛", "期望进球 xG 推导",
    "收缩系数", "后验", "先验",
]

EXPLAINER_SENTENCES = [
    "主队在左", "客队在右", "怎么看这张表", "最好按其余球队",
    "荣誉是公开慢变量", "数据来源说明", "如何阅读",
]

BETTING_WORDS = [
    "必中", "稳赚", "内幕", "包中", "推荐买入", "跟着买", "稳赢", "红单",
]

# ---- §3.3 评级词表：只允许这几个词 ----
ALLOWED_GRADES = ("可用", "慎用", "别跟")

# 出现这些近似词说明词表走偏了
GRADE_DRIFT = ["推荐指数", "买入评级", "值得投", "不建议投", "建议投注"]

# ---- 概率渲染：搜集所有裸百分比 ----
PERCENT_RE = re.compile(r"\d+(?:\.\d+)?%")
PCT_TAG_RE = re.compile(r'class="pct[^"]*"[^<]*<[^<]*?(\d+(?:\.\d+)?%)')


@dataclass
class Violation:
    file: str
    line: int
    rule: str
    snippet: str


def _iter_html(out_dir: Path):
    for p in sorted(out_dir.rglob("*.html")):
        yield p


def _scan_text(rel: str, text: str, *, ignore_quoted_words: bool = True) -> list[Violation]:
    out: list[Violation] = []
    lines = text.split("\n")
    for i, line in enumerate(lines, 1):
        low = line
        checks: list[tuple[str, list[str]]] = [
            ("内部术语", INTERNAL_TERMS),
            ("推演痕迹", REASONING_TRACE),
            ("说明句", EXPLAINER_SENTENCES),
            ("投注诱导", BETTING_WORDS),
            ("评级词漂移", GRADE_DRIFT),
        ]
        for rule, words in checks:
            for w in words:
                if w.lower() in low.lower():
                    out.append(Violation(rel, i, rule, (w, line.strip()[:120])[1]))
                    break
    return out


def _scan_percents(rel: str, text: str) -> list[Violation]:
    """§3.2：概率数字必须走 prob_tag()，不允许裸写。

    判定：找到形如 `12.3%` 的位置，向前回看 120 个字符，若其间没有出现
    `class="pct` 则视为裸写。CSS/行内样式里的百分比不计（那是宽度不是概率）。
    """
    out: list[Violation] = []
    for i, line in enumerate(text.split("\n"), 1):
        if "<style" in line or "width:" in line or "fill-opacity" in line:
            continue
        for m in PERCENT_RE.finditer(line):
            # 排除 CSS 属性中的百分比
            head = line[max(0, m.start() - 120): m.start()]
            if "class=\"pct" in head and head.rfind('class="pct') > head.rfind("<td"):
                continue
            if any(k in head[-30:] for k in ("width:", "opacity", "%") ):
                continue
            out.append(Violation(rel, i, "裸百分比", line.strip()[:120]))
            break
    return out


def check_site(out_dir: Path) -> list[Violation]:
    res: list[Violation] = []
    if not out_dir.exists():
        return [Violation(str(out_dir), 0, "目录缺失", "构建产物目录不存在")]
    for p in _iter_html(out_dir):
        rel = str(p.relative_to(out_dir)).replace("\\", "/")
        text = p.read_text(encoding="utf-8")
        res += _scan_text(rel, text)
        res += _scan_percents(rel, text)
    return res


def report(violations: list[Violation]) -> str:
    if not violations:
        return "红线自检通过：0 项违规。"
    buckets: dict[str, list[Violation]] = {}
    for v in violations:
        buckets.setdefault(v.rule, []).append(v)
    lines = [f"红线自检发现 {len(violations)} 项违规："]
    for rule, vs in sorted(buckets.items(), key=lambda x: -len(x[1])):
        lines.append(f"\n[{rule}] {len(vs)} 项")
        for v in vs[:8]:
            lines.append(f"  {v.file}:{v.line}  {v.snippet}")
        if len(vs) > 8:
            lines.append(f"  ... 另有 {len(vs) - 8} 项")
    return "\n".join(lines)
