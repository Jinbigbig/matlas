# 高清局部截图：双方页头/侧栏/卡片/页脚
from playwright.sync_api import sync_playwright

SHOTS = [
    # (选择器, 输出名)
    ("header.header", "header"),
    (".site-disclaimer", "disclaimer"),
    (".v4-filter-bar", "filterbar"),
    (".match-card", "card"),
    (".right-sidebar-new, .widget, aside", "sidebar"),
    ("footer.site, footer", "footer"),
]

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    for tag, url in [("qxc", "https://www.qiuxiaoce.com/"), ("matlas", "http://127.0.0.1:8799/index.html")]:
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(2500)
        for sel, name in SHOTS:
            el = pg.query_selector(sel)
            if el:
                try:
                    el.screenshot(path=f"C:/tmp/z_{tag}_{name}.png")
                    print(tag, name, "ok")
                except Exception as e:
                    print(tag, name, "ERR", str(e)[:80])
            else:
                print(tag, name, "MISSING")
        # 对方侧栏完整 HTML 供结构 diff
        if tag == "qxc":
            aside = pg.evaluate("""() => {
                const a = document.querySelector('.home-v4-scope aside, .sidebar, #sidebar, .widget-area');
                return a ? a.outerHTML.slice(0, 12000) : 'NO ASIDE';
            }""")
            open("C:/tmp/z_qxc_aside.html", "w", encoding="utf-8").write(aside)
    b.close()
print("done")
