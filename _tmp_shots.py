# 截图自检：新页头/筛选面板/四个落地页
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8799"

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1280, "height": 900})

    # 1. 首页：默认态（筛选面板收起）
    pg.goto(f"{BASE}/index.html")
    pg.wait_for_load_state("networkidle")
    pg.screenshot(path="C:/tmp/v4_home.png")

    # 2. 点击「🔍 筛选」展开面板
    pg.click("label.v4-filter-btn")
    pg.wait_for_timeout(300)
    pg.screenshot(path="C:/tmp/v4_filter_open.png")

    # 3. 点欧冠单选验证过滤
    pg.click("label[for='lf-1']")
    pg.wait_for_timeout(300)
    n_visible = pg.evaluate(
        "() => [...document.querySelectorAll('.match-card')]"
        ".filter(c => getComputedStyle(c).display !== 'none').length"
    )
    print("欧冠筛选后可见卡片:", n_visible)

    # 4. 点搜索图标展开搜索层
    pg.click("label.nav-search")
    pg.wait_for_timeout(300)
    pg.screenshot(path="C:/tmp/v4_search_open.png")

    # 5. 四个落地页
    for name in ("data", "features", "me", "search"):
        pg.goto(f"{BASE}/{name}.html")
        pg.wait_for_load_state("networkidle")
        pg.screenshot(path=f"C:/tmp/v4_{name}.png")

    # 6. 搜索页带关键字
    pg.goto(f"{BASE}/search.html?q=拜仁")
    pg.wait_for_load_state("networkidle")
    print("搜索拜仁结果:", pg.evaluate("() => document.querySelectorAll('#search-results .match-card').length"))
    pg.screenshot(path="C:/tmp/v4_search_q.png")

    b.close()
print("ok")
