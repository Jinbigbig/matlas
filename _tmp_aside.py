# 抓对方侧栏「赛事Top10 / 球队Top10」真实 HTML 结构
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto("https://www.qiuxiaoce.com/", wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_timeout(2500)
    html = pg.evaluate("""() => {
        // 找到含「赛事Top 10」文字的卡片，取其父容器整块
        const els = [...document.querySelectorAll('div')];
        const card = els.find(e => e.className && String(e.className).includes('card')
            && e.textContent.includes('赛事Top 10') && e.textContent.includes('球队Top 10'));
        return card ? card.outerHTML.slice(0, 15000) : 'NOT FOUND';
    }""")
    open("C:/tmp/z_qxc_topcards.html", "w", encoding="utf-8").write(html)
    print(len(html))
    b.close()
