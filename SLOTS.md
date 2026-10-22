# 槽位登记表

> 本文件由 `matlas/slots.py` 生成，**不要手改** —— 改代码里的 `SLOTS` 再重新生成。
> 当前：槽位 16 个：已接线 13 / 待接线 2 / 待开发 1

框架（渲染层）已为每个槽位铺好，缺数据时该块自动不渲染；
数据由谁供、什么时候供，全部记在这张表里。换源只改本表和对应适配器。

| 状态 | 模块 | 契约字段 | 数据来源（按优先级） | 备注 |
| --- | --- | --- | --- | --- |
| ⏸ | **队徽** | `Team.logo` | jinbet 球队字典（尚无 logo 字段） | 渲染层已接线且带协议校验（只放行 http(s)/相对路径）；无 logo 时退化为纯文字，不留占位框。缺的是数据源，不是框架 |
| ✅ | **主推** | `Match.main_pick` | jinbet V3.4 引擎结论摘要 | 一句话主推，页面第一视觉重心；缺则整块不出现 |
| ✅ | **置信度** | `Match.confidence` | jinbet 引擎 | 词表固定 高/中/低/冷门 |
| ✅ | **四宫格结论** | `Match.forecasts[]` | jinbet 引擎 V3.4 | 方向/比分/进球/半全场，各带首选+次选与概率 |
| ✅ | **让球结论** | `Match.handicap` | jinbet 让球分级（RULES §3.3 阈值已定） | 盘口赔率在 Odds.handicap*，结论在 Handicap，两者分离 |
| ✅ | **风险提示** | `Match.risk` | jinbet 冷门过滤 / 风险否决<br>人工标注 | 三档 info/warn/block；block 不隐藏页面，留档必须完整 |
| ✅ | **六维战力雷达** | `Match.metrics_home / metrics_away` | jinbet 引擎六维 | 轴：进攻/防守/控制/状态/阵容/战意（与球小策 radar 六轴同名） |
| ✅ | **进球威胁度走势** | `Match.momentum` | jinbet λ 曲线离散化 | 7 点标签 0'~90'，与球小策 momentum 同构 |
| ⏸ | **市场数据** | `Match.odds` | 竞彩官方<br>7M<br>腾讯体育 | **没有任何抓取适配器** —— 现在只能靠上游写进 JSON |
| ✅ | **积分排名** | `Team.rank/points/played/win/draw/loss/gf/ga` | 腾讯 matchweb rank/listV2<br>Fox Sports SSR<br>7M<br>懂球帝 standing | 四个源在 jinbet 侧已验证可用，Matlas 侧只消费字段 |
| ✅ | **历史交锋** | `Match.h2h[]` | 懂球帝 pre_analysis_v1<br>香港赛马会赛前简报<br>results_data.json |  |
| ✅ | **近期战绩** | `Match.recent_home / recent_away[]` | results_data.json（官方赛果库，自 2025-12-31） |  |
| ✅ | **伤停与缺阵** | `Match.injuries[]` | lineupstoday<br>香港赛马会赛前简报<br>德甲/荷甲官方 |  |
| ✅ | **外部对照** | `Match.reference` | 球小策开源数据集 ddzyx/qiuxiaoce-football-data（CC BY-NC 4.0，每日约 3 场）<br>Agent Skill: qiuxiaoce-football-data@2.14.0（/match-pack/{id}，50 点/场） | 只做比对，永不参与本站概率计算；必须署名留链 |
| ✅ | **留档核验** | `Match.fingerprint()` | 本地计算 sha256 | 只覆盖赛前字段，赛后回填不改变指纹 |
| ❌ | **赛果结算** | `Match.result` | 官方赛果源（results_data.json 等） | **目标缺口**：result.*_hit 目前靠人工填，没有 settle 函数按比分自动判定 |

## 状态含义

- ✅ **ready**：渲染层已接、契约已通。今天没数据只会让该块消失，不影响构建。
- ⏸ **pending**：契约留了位，但还没有任何源往里写。
- ❌ **todo**：连生成逻辑都没有，需要新写代码。

## Agent Skill 记号

球小策的官方 Skill 包（`qiuxiaoce-football-data`）可作为外部对照与高阶指标的候补源，
接入方式与计费已在调研中记录，**当前不启用**，仅在上表第 13 项留位。
