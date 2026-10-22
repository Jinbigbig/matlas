# Matlas

**Matlas（Match Atlas · 赛图）** —— 足球赛事量化图谱，纯静态发布层。

源码与 jinbet **完全分离**，规则与 jinbet **完全一致**（见 [RULES.md](RULES.md)）：

```
jinbet  →  负责「算」：V3.4 引擎、Platt 校准、Brier_opt / Kalman
Matlas  →  负责「发」：per-match 落地页、留档核验、llms.txt / sitemap / Schema.org
           ↑ 两者唯一的耦合是数据契约（models.py），不互相 import
```

## 快速开始

```bash
python import_jinbet.py         # 从 jinbet 导入预测/赛果/积分/盘口 → data/days/
python build.py                 # 构建 data/days 下全部交易日 → _site/
python build.py --strict        # 红线命中即以非零码退出（CI 用）
python build.py --slots         # 重新生成 SLOTS.md 并打印槽位接线状态
```

零依赖、零 CDN、离线可跑。Python 3.10+。

## 分支与发布

| 分支 | 内容 | 本地位置 |
| --- | --- | --- |
| `main` | 源码 + 数据 | 工作区 `<repo>/`（`_site/`、`.publish/` 均被 .gitignore） |
| `gh-pages` | 构建产物 | 工作树 `<repo>/.publish/`（一个提交 = 一次发布） |

```bash
git worktree add .publish gh-pages   # 首次：建产物工作树
./publish.sh                         # 构建（strict）→ 同步到 .publish → 提交 → 推送
./publish.sh --no-push               # 只构建到 _site，不动产物分支
```

发布脚本的安全阀：工作区有未提交改动时拒绝发布；`.publish` 不在 `gh-pages` 分支时拒绝写入。

**线上地址**：<https://jinbigbig.github.io/matlas/>（canonical / sitemap / llms.txt 全部指向这里）。
域名只在 `matlas/config.py::DEFAULT_BASE_URL` 定义一处，换域名只改这一行再发布。

## 功能

| 能力 | 说明 |
| --- | --- |
| **每日赛事前瞻** | 首页卡片列表 + 时间滚动条切换日期 + 类型/赛事筛选（纯 CSS，无 JS 依赖） |
| **per-match 落地页** | 每场独立 URL：`matches/<match_id>.html`，可被搜索引擎与 AI 单独索引 |
| **四宫格结论** | 方向 / 比分 / 进球 / 半全场，各带首选与次选概率与命中标记 |
| **赛前情报与积分** | 赛前情报速览、核心数据对比、积分排名（腾讯五联赛 + 欧战三源） |
| **近期战绩 / 历史交锋** | 赛前视角聚合（时间截断不穿越），含半全场结果列与胜平负圆点 |
| **AI 预测卡** | 右栏：最近 6 个交易日的四维预测首选，时间/赛事筛选 |
| **赔率页** | 竞彩盘口快照浏览（胜平负 / 让球 / 进球数），按日期切换，附赛果对照 |
| **投注记录本** | localStorage 记录 + 内嵌赛果自动结算（赢/输/走水/待开赛）与盈亏统计 |
| **数据统计** | 总场次 / 四维准确率 / 近10天走势 / 球队表现查询 / 联赛与球队 Top 榜 |
| **联赛 / 球队专题页** | `leagues/*.html`、`teams/*.html`，数据随导入自动生长 |
| **历史归档三视图** | 交易日 / 联赛 / 球队，`days/*.html` 逐日留档 |
| **站内搜索** | 按队名、联赛、竞彩编号检索全部历史赛事（前端过滤，无后端） |
| **结论指纹** | 覆盖赛前全部结论字段的 SHA-256 前 12 位，赛后回填不改变该值 |
| **纯 SVG 可视化** | 六维战力雷达 + 0–90 分钟进球威胁度曲线，无第三方 JS |
| **GEO 基建** | `llms.txt` / `robots.txt` / `sitemap.xml` / `dataset.json` / Schema.org |
| **红线自检** | `matlas/rules.py` 构建后自动扫描产物，见下方规则清单 |

## 数据来源

数据经 `import_jinbet.py` 从 jinbet 项目导入（可重复执行，幂等）：

| 源 | 内容 |
| --- | --- |
| `predictions/{date}/pred_snapshot.json` | 预测快照：方向/比分/进球/半全场、λ、冷门、让球结论 |
| `results_history/{date}.json`（缺失时回退 `results_data.json`） | 赛果回填：半场/全场比分与各维命中 |
| `qq_standings.json` + `fox_standings.json` + `uefa_standings.json` | 积分榜：五联赛 + 欧罗巴/解放者杯/欧协联 |
| `scripts/matches_data.json` | 当日网易赛前近况（gf/ga 序列）与盘口 |

队徽库离线自球小策公开队徽库（`assets/logo/teams/`，按编号引用），映射表见 `matlas/logos.py`。

## 数据契约

唯一对外接口，定义在 [matlas/models.py](matlas/models.py)。上游只要产出符合它的 JSON 即可接入：

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
缺字段自动降级：任何维度缺失，对应区块不出现，不做补白。

## 构建期规则

`matlas/rules.py` 在每次构建结束后扫描 `_site/**/*.html`，违规即报文件名与行号（`--strict` 时非零退出）。

| 规则 | 内容 |
| --- | --- |
| 内部术语 | 不得出现 目标函数 / 口径一致性 / 偏差归因 / probe / χ² / Brier / argmax / McNemar 等 |
| 推演痕迹 | 不得出现 λ= / 校准后 / 零封修正 / 泊松 / 蒙特卡洛 等推导过程 |
| 说明句 | 不写「怎么看这张表」这类解释，数据缺口只给最短一句 |
| 投注诱导 | 不得出现 必中 / 稳赚 / 内幕 / 包中 等 |
| 概率渲染 | 必须走 `prob_tag()`；阈值 ≥60% 强 / 45–60% 中 / <45% 弱，统一 1 位小数 |
| 评级词表 | 只允许 **可用 / 慎用 / 别跟** |
| 留档不可篡改 | 赛后回填不得改变结论指纹 |

## 目录

```
matlas/
├── RULES.md          项目定义 + 继承规则（必读）
├── SLOTS.md          槽位登记表（由 matlas/slots.py 生成）
├── build.py          构建入口
├── import_jinbet.py  jinbet 数据导入（预测/赛果/积分/盘口）
├── publish.sh        发布脚本（strict 构建 → .publish → 推送 gh-pages）
├── matlas/
│   ├── models.py     数据契约 ← 唯一对外接口
│   ├── rules.py      红线自检
│   ├── logos.py      队名 → 队徽编号映射
│   ├── config.py     站点身份与路径
│   ├── pipeline.py   构建流水线
│   ├── seo.py        llms.txt / robots / sitemap / 数据快照
│   ├── source/       数据源适配层（插件式）
│   └── render/       布局 / 组件 / 页面
├── assets/logo/      队徽与赛事徽章（离线快照）
├── data/days/        每日数据（git 留档）
└── _site/            构建产物（gitignored）
```
