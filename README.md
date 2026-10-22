# Matlas

**Matlas（Match Atlas · 赛图）** —— 足球赛事量化图谱，纯静态发布层。

源码与 jinbet **完全分离**，规则与 jinbet **完全一致**（见 [RULES.md](RULES.md)）。

```
jinbet  →  负责「算」：V3.4 引擎、Platt 校准、Brier_opt / Kalman
Matlas  →  负责「发」：per-match 落地页、留档核验、llms.txt / sitemap / Schema.org
           ↑ 两者唯一的耦合是数据契约（models.py），不互相 import
```

---

## 快速开始

```bash
python build.py                 # 构建 data/days 下全部交易日 → _site/
python build.py --strict        # 红线命中即以非零码退出（CI 用）
python build.py --reference 2026-10-22   # 额外并入第三方对照（需联网，默认关）
```

零依赖、零 CDN、离线可跑。Python 3.10+。

---

## 分支与发布

| 分支 | 内容 |
| --- | --- |
| `main` | 源码 + 数据（`_site/` 已在 .gitignore 里，产物永不进 main） |
| `gh-pages` | 构建产物，GitHub Pages 从这里出 |

```bash
./publish.sh              # 构建（strict）+ 推送 gh-pages
./publish.sh --no-push    # 只构建，本地预览
```

发布脚本会先检查工作区是否有未提交改动 —— 有就拒绝发布，避免产物里夹带源码改动。

### 线上地址

| 入口 | URL | 用途 |
| --- | --- | --- |
| **主站** | <https://jinbigbig.github.io/matlas/> | GitHub Pages，公开可抓取，canonical / sitemap / llms.txt 全部指向这里 |
| 预览镜像 | `https://matlas.app.workbuddy.host/?sharecode=…` | 内置发布通道，**裸路径 403**，仅供人工预览 |

域名只在 `matlas/config.py::DEFAULT_BASE_URL` 定义一处，渲染层（canonical / og / JSON-LD / sitemap / robots / llms.txt）全部由它派生。
换域名只改这一行再 `./publish.sh`，或临时覆盖：`python build.py --base-url https://example.com`。

> canonical 必须是不带任何参数就能打开的地址。带 `?sharecode=` 的链接对爬虫等于 403，会造成整站索引失效。

---

## 它已经能做什么

| 能力 | 说明 |
| --- | --- |
| **per-match 落地页** | 每场独立 URL：`matches/<match_id>.html`，可被搜索引擎与 AI 单独索引 |
| **四宫格结论** | 方向 / 比分 / 进球 / 半全场，各带首选与次选概率 |
| **纯 SVG 可视化** | 六维战力雷达 + 0–90 分钟进球威胁度曲线，无第三方 JS |
| **结论指纹** | 覆盖赛前全部结论字段的 SHA-256 前 12 位，赛后回填不改变该值 |
| **GEO 基建** | `llms.txt` / `robots.txt` / `sitemap.xml` / `sitemap-today.xml` |
| **Schema.org** | 每页输出 `Article` + `SportsEvent`，列表页输出 `CollectionPage` + `ItemList` |
| **数据快照** | `data/dataset.json` 全量 + `data/days/*.json` 逐日，便于 diff 出结论变动 |
| **红线自检** | `matlas/rules.py` 构建后自动扫描产物，见下方规则清单 |
| **缺字段降级** | 任何维度缺失自动省略对应区块，不做补白、不写解释句 |

---

## 数据契约

唯一对外接口，定义在 [matlas/models.py](matlas/models.py)。上游只要产出符合它的 JSON：

```json
{
  "match_id": "2026-10-22-004",
  "code": "周三004",
  "competition": "欧冠",
  "kickoff": "2026-10-22 00:45",
  "home":  { "name": "科莫", "rank": 8, "points": 12, "form": "WWDLW" },
  "away":  { "name": "曼彻斯特联", "rank": 9, "points": 11, "form": "DDLDL" },
  "odds":  { "home": 2.10, "draw": 3.60, "away": 3.30 },
  "forecasts": [
    { "kind": "direction", "label": "主胜", "prob": 0.482, "rank": 1 },
    { "kind": "score",     "label": "2-1",  "prob": 0.148, "rank": 1 }
  ],
  "confidence": "medium",
  "result": { "half_score": "1-0", "full_score": "4-1", "direction_hit": true }
}
```

`forecasts` 的 `kind` 限定 `direction | score | goals | htft`；
`confidence` 限定 `high | medium | low | none`；其余字段全可选。

把 jinbet 的 `_calc_result.json` 转成这个形状即可接入 —— 转换脚本**不在本项目范围内**，等你下一步指示。

---

## 继承的规则（构建期强制）

`matlas/rules.py` 在每次构建结束后扫描 `_site/**/*.html`，违规即报文件名与行号。

| 规则 | 内容 |
| --- | --- |
| 内部术语 | 不得出现 目标函数 / 口径一致性 / 偏差归因 / probe / χ² / Brier / argmax / McNemar 等 |
| 推演痕迹 | 不得出现 λ= / 校准后 / 零封修正 / 泊松 / 蒙特卡洛 等推导过程 |
| 说明句 | 不写「怎么看这张表」这类解释，数据缺口只给最短一句 |
| 投注诱导 | 不得出现 必中 / 稳赚 / 内幕 / 包中 等 |
| 概率渲染 | 必须走 `prob_tag()`；阈值 ≥60% 强 / 45–60% 中 / <45% 弱，统一 1 位小数 |
| 评级词表 | 只允许 **可用 / 慎用 / 别跟** |
| 留档不可篡改 | 赛后回填不得改变结论指纹 |

---

## 目录

```
matlas/
├── RULES.md          项目定义 + 继承规则（必读）
├── build.py          构建入口
├── matlas/
│   ├── models.py     数据契约 ← 唯一对外接口
│   ├── rules.py      红线自检
│   ├── config.py     站点身份与路径
│   ├── pipeline.py   构建流水线
│   ├── seo.py        llms.txt / robots / sitemap / 数据快照
│   ├── source/       数据源适配层（插件式）
│   └── render/       布局 / 组件 / 页面
├── data/days/        每日数据
└── _site/            产物（gitignored）
```

---

## 没做的部分

按你的要求，**可能冲突或需要你定夺的一律没动**，全部列在 [RULES.md §5](RULES.md)：

- ⏸ 接 jinbet V3.4 引擎（契约已预留）
- ⏸ 赔率 / 7M / 腾讯 / Fox / lineupstoday 抓取
- ⏸ SCORE_ALIGN 比分口径、让球分级、冷门过滤
- ⏸ 第三方对照源（适配器已写好，默认关闭）
- ❌ 明确不做：LLM 长文（与文案红线冲突）、任何运行时依赖

等你的下一步指示。
