# 球小策（qiuxiaoce.com）渲染与结构实测分析

> 实测时间：2026-10-22 13:0x　方法：抓源码 + 解析 DOM/CSS，不做推测
> 结论先给：**视觉上与 Matlas 几乎没有一处相同**。此前「结构同构」的判断
> 建立在 API 返回的 JSON 字段上，不是页面渲染结果 —— 官网页面上那些图表根本不存在。

---

## 0. 一句话纠正

之前说的「六轴雷达同构」来自 `charts.radar` 这个 **API 数据字段**。
官网单场页正文实测：`<svg>` 0 个、`<canvas>` 0 个、`<img>` 0 个。
**它不渲染雷达图、不渲染曲线。** 数据里有，页面上没有。

---

## 1. 技术栈

| 项 | 实测值 |
| --- | --- |
| CMS | WordPress 6.8.1 |
| 主题 | `dux` 8.2.1.30（第三方商业主题） |
| 自研插件 | `abv2-football-info` 0.1.2、`abv2-unified-auth` 1.2.5、`abv2-admin-dashboard` |
| 外部 CSS | 8 个 stylesheet，合计约 48 KB |
| 内联 `<style>` | 7 块，13 KB |
| `<script>` | 首页 23 个 |
| 渲染方式 | 服务端 PHP 拼装 + 内联 `onclick` + 12 处 `addEventListener` |

关键样式表：

```
themes/dux/assets/css/home-v4.css            18.8 KB  首页布局
themes/dux/assets/css/prediction-result.css   7.8 KB  命中印章
plugins/abv2-football-info/assets/css/frontend.css  17.7 KB  比赛卡片
plugins/abv2-football-info/assets/css/team-stats-enhanced.css  4.3 KB
```

---

## 2. 设计系统（可量化部分）

| Token | 球小策 | Matlas | 判定 |
| --- | --- | --- | --- |
| 主色 | `#2563eb`（Tailwind blue-600） | `#e63946`（红） | ❌ 完全不同 |
| 强调色 | `#f59e0b` 琥珀 / `#10b981` 翠绿 / `#dc2626` 红 | `#2a9d8f` 青 / `#f4a261` 橙 | ❌ |
| 页面底色 | `#f5f7fa` | `#f0f2f5` | ⚠️ 仅数值近，观感同级 |
| 卡片底 | `#fff` | `#fff` | ✅ 通用做法 |
| 圆角主力 | `8px`（25 次）→ `4px`(11) `12px`(9) | `4px`（10 次）→ `8px`(6) `10px`(5) | ⚠️ 取向相近，主力值相反 |
| 字号主力 | `12px`(26) `13px`(20) `14px`(19) | `0.8rem`(9) `0.85rem`(7) `0.75rem`(6) ≈12.8/13.6/12px | ✅ 数值区间重合 |
| 阴影 | `0 1px 3px rgba(0,0,0,.05)` | `0 1px 3px rgba(0,0,0,.06)` | ✅ 几乎同款 |
| 字体栈 | `-apple-system, sans-serif` | `-apple-system, BlinkMacSystemFont, 'Segoe UI'…` | ✅ 同为系统栈 |
| 断点 | `480 / 640 / 768 / 1200`（外加 `80/100` 用于打印类） | **0 个 media query** | ❌ 我们完全没有响应式 |

**真实相同项只有三项**：系统字体栈、极轻阴影（0.05 vs 0.06）、12–14px 小字。
这三项属于「中文资讯站通用基线」，不构成风格抄袭，也**不足以**说「样式一样」。

**真正决定观感的三项全部不同**：主色（蓝 vs 红）、圆角梯度、有无响应式。

---

## 3. 首页结构

```
<body>
 ├ header.header           .logo + .brand + ul.site-nav
 ├ div.m-icon-nav          移动端图标导航
 ├ div.site-search
 ├ div.home-v4-scope
 │   ├ div.v4-main-col                       ← 主列
 │   │   ├ div#panel-matches.panel-matches   ← Tab 1：赛事
 │   │   │   ├ div.site-disclaimer
 │   │   │   ├ div.v4-filter-bar             📅 10月21日 (13场) + 🔍 筛选
 │   │   │   ├ div#filter-panel             类型: 全部/竞彩/北单（可折叠）
 │   │   │   └ div#matches-list              a.match-card × N
 │   │   └ div#panel-functions               ← Tab 2：功能
 │   │       └ div.v4-func-grid
 │   └ div.right-sidebar-new                 ← 桌面侧栏
 │       ├ div.checkin-info / .checkin-icon  签到
 │       ├ div.right-promo-banners          推广位 ×2
 │       ├ div#league-ranking-card           联赛排行
 │       └ div#team-ranking-card             球队排行
 ├ div.v4-bottom-nav-global                 ← 移动端固定底部导航（4 项）
 ├ footer.footer
 ├ div.karbar.karbar-rb                     ← 悬浮工具条
 └ div.sign                                 ← 登录/签到弹层
```

要点：
- **双栏**（主列 1fr + 右侧栏），桌面 1200px 断点收起侧栏
- **Tab 切换**：`panel-matches` / `panel-functions` 用 `.active` 类切换，不是路由
- **移动优先**：`.v4-bottom-nav-global` 桌面 `display:none`，≤768px 显示，60px 高 + `env(safe-area-inset-bottom)`
- 是**运营型门户**，不是纯内容站：签到、排行、推广位都在首屏侧栏

### 比赛卡片 DOM

```html
<a class="match-card filter-item" data-type="jingcai" data-league="解放者杯">
  <div class="mc-header">
    <div class="mc-meta">
      <span class="date">10/22</span>
      <span class="league">解放者杯</span>
      <span class="num">周三013</span>
      <span class="time">08:30</span>
    </div>
    <div class="mc-status">
      <span class="mc-conf medium">AI置信度:中</span>
      <div class="prediction-stamp stamp-red">✔</div>
    </div>
  </div>
  <div class="mc-body">
    <div class="mc-teams">
      <div class="mc-team"><img src="…/logo/teams/121.png"><span>帕尔梅拉斯</span></div>
      <div class="mc-score"><div class="main">0-1</div><div class="sub">(0-0)</div></div>
      <div class="mc-team"><img src="…/logo/teams/124.png"><span>弗鲁米嫩</span></div>
    </div>
    <div class="mc-tags">
      <div class="mc-tag">🧭 方向</div>
      <div class="mc-tag hit">⚽ 进球</div>
      <div class="mc-tag">🔢 比分</div>
      <div class="mc-tag">📈 半全</div>
    </div>
    <div class="mc-footer">
      <span class="mc-highlight-icon">💡</span>
      <span class="mc-highlight-text">决战南美之巅…</span>
    </div>
  </div>
</a>
```

三个我们**没有**的元素：**队徽 `<img>`**、**置信度徽章**、**卡片底部一句话亮点**。
（`.mc-tag.hit` 命中加亮 —— 与我们 `.pick` 思路接近，但它是 emoji + 独立标签）

---

## 4. 单场页结构

```
body
 ├ div.breadcrumbs
 ├ div.content-wrap.content
 │   ├ div.prediction-stamp.stamp-red     ← 命中印章（页面级）
 │   ├ div.article-meta
 │   ├ article.article-content            ← 正文主体，26.5 KB HTML
 │   │   ├ div.article-disclaimer-top
 │   │   ├ div.related-post-notice
 │   │   ├ div.mscg-share-wrapper          “登录生成海报”（需登录）
 │   │   ├ div.mef-rec-container           ← 结论卡（全内联 style）
 │   │   ├ div.table-container             × 3 个 table
 │   │   └ div.article-disclaimer-bottom
 │   ├ div.league-related / .post-actions / .post-copyright / .shares
 │   ├ div.article-tags
 │   └ div.relates.relates-imagetext
 └ div.sidebar（widget_ui_posts / widget_ui_tags / widget_ui_statistics）
```

### 正文是一篇长文，不是结论面板

章节（h2 / h3 实测）：

```
h2 📌 帕尔梅拉斯 vs 弗鲁米嫩：赛前情报速览
h2 📊 1. 攻防解构 vs 战术反制
   h3 ⚔️ 历史交锋数据
   h3 📈 球队状态与战术风格解析
   h3 🔍 核心数据对比：xG场均差0.78球
   h3 🔬 高阶数据对比
   h3 ⚠️ 核心球员缺阵影响评估
   h3 ⚖️ 裁判执法数据分析
h2 🤔 2. 三个角度看胜负天平
h2 🧠 3. 模型视角下的数据答案
h2 🎯 4. 综合赛果推演
   h3 🔑 4.1 核心观点研判
   h3 🔥 4.2 进球数概率推演
   h3 🥅 4.3 终场比分概率矩阵
   h3 ⏳ 4.4 半场/全场走势概率
   h3 ⏳ 4.5 比赛进程与战术节点推演
   h3 🚩 4.6 定位球博弈前瞻
   h3 🚩 4.7 角球与定位球博弈前瞻
   h3 ❓ 量化数据答疑 (FAQ)
```

**比分矩阵 / 半全场其实是「文字 + emoji 序号」**，没有矩阵网格：

```html
<p>1️⃣ <strong>概率首选:</strong> 2-0 <strong>(模型概率: 15.2%)</strong></p>
<ul><li><p><strong>矩阵分析：</strong> 弗鲁米嫩在落后局面下…（约 100 字散文）</p></li></ul>
<p>2️⃣ <strong>概率次选:</strong> 1-0 <strong>(模型概率: 13.8%)</strong></p>
```

差异本质一句话：
**它是「一个数字 + 一段解释」，我们是「一个数字 + 一个可复算的图形」。**

### 视觉实现方式：内联硬编码

```
正文内 style= 属性：73 处
正文内 class= 属性：17 处
```

结论卡全程内联：

```html
<div class='mef-rec-container' style='padding:20px; border:1px solid #e8e8e8;
  border-radius:12px; background:#fff; box-shadow:0 4px 16px rgba(0,0,0,0.04);'>
  <span style='background:#ff9900;color:#fff;padding:6px 16px;border-radius:6px;'>AI置信度：中</span>
  <span style='background:#ffe6e6;color:#dc3232;border:1px solid #dc3232;'>进球数正确</span>
```

→ 无设计 token 层，改色要改 PHP 拼接处；同一语义在不同页面会出现 `#dc3232` 与 `#dc2626` 两个红。

### 三张表（唯一的结构化对比）

1. 历史交锋：日期 / 赛事 / 主队 / 比分(半场) / 客队
2. 赛季数据：xG、xGA、控球率、射门、射正、场均角球
3. 高阶指标：`FW-OTI` 锋线攻击力、`DF-DII` 防守参与度、`MF-OTI` 中场创造力、
   `GIM` 核心影响力、`Form` 即时战力 —— **带差值列**（如 `+17.2`）

第 3 张表的「维度 + 双方数值 + 优势分析」三列结构，是我们值得直接借鉴的排布。

---

## 5. 与 Matlas 的结构对照

| 维度 | 球小策 | Matlas | 差距性质 |
| --- | --- | --- | --- |
| 页面形态 | 内容门户（Tab + 侧栏 + 签到 + 排行） | 结论台账（单列卡片） | 定位不同，不必抄 |
| 单场页 | 长文 26 KB，4 章 15 节 | 卡片式，结论优先 | **核心差异** |
| 图表 | 0 SVG / 0 canvas / 0 img | 纯 SVG 雷达 + 0–90′ 曲线 | **我们领先** |
| 样式层 | 73 内联 style | 16 KB 集中 CSS + class | **我们领先** |
| 队徽 | 有 `<img>` 队徽 | 纯文字队名 | 我们缺 |
| 置信度 | 独立徽章 `.mc-conf` | `mp-tag` 文本 | 我们弱 |
| 卡片亮点句 | `.mc-highlight-*` + 💡 | `main_pick` 条 | 等价 |
| 筛选 | 类型（竞彩/北单）可折叠面板 | 无 | 我们缺 |
| 移动端 | 底部导航 + safe-area | **0 个 media query** | **硬伤** |
| 命中标记 | 印章 `.prediction-stamp`（页级） | `result.*_hit` 四布尔 | 它更视觉化 |
| 数据可信 | 内联硬编码，`is_correct` 自相矛盾 | 指纹 v1 可核验 | **我们领先** |

---

## 6. 应当借鉴的五点（按性价比排序）

1. **补响应式（最急）** —— 我们 0 个 `@media`，手机上必然是挤压/溢出。
   先做 `768px` 单断点：`.cards` 单列、`.picks4` 两列、隐藏副标题。
2. **队徽图片** —— 卡片视觉识别度提升最明显的一项。需要 `team.logo_url` 槽位。
3. **置信度做成独立徽章 + 三档配色**（高/中/低），而不是塞在正文小字里。
4. **页面级命中印章** —— 赛后状态用一枚角标表达，比四个布尔字面更有力。
5. **筛选栏**（类型/联赛）—— 场次变多后必要，但要等数据侧有 league 维度。

**不借鉴**：双栏 + 签到 + 排行榜 + 推广位。那是运营门户的产物，
与「可核验台账」的定位冲突，且会稀释单场结论的信息密度。

---

## 7. 复现命令

```bash
# 首页与单场页
curl -sL "https://www.qiuxiaoce.com/" -o home.html
curl -sL "https://www.qiuxiaoce.com/zhou-san-013-pa-er-mei-la-si-vs-fu-lu-mi-nen-sai-qian-fen/" -o match.html

# 样式表
curl -s "https://www.qiuxiaoce.com/wp-content/themes/dux/assets/css/home-v4.css?ver=8.2.1.30" -o home-v4.css
curl -s "https://www.qiuxiaoce.com/wp-content/themes/dux/assets/css/prediction-result.css?ver=8.2.1.30" -o prediction-result.css
curl -s "https://www.qiuxiaoce.com/wp-content/plugins/abv2-football-info/assets/css/frontend.css?ver=0.1.2" -o frontend.css

# 关键校验：正文里有无图表
python -c "import re;t=open('match.html',encoding='utf-8').read();a=t[t.find('<article'):t.find('</article>')];print('svg',len(re.findall(r'<svg[\s>]',a)),'canvas',len(re.findall(r'<canvas[\s>]',a)))"
```
