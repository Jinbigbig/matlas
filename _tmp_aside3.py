# 输出对方侧栏 ranking-item 完整结构（赛事Top 与 球队Top 各取 2 项）
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto("https://www.qiuxiaoce.com/", wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_timeout(2500)
    out = pg.evaluate("""() => {
        const sidebar = document.querySelector('.right-sidebar-new');
        if (!sidebar) return 'NO SIDEBAR';
        const cards = sidebar.querySelectorAll(':scope > .ranking-card, :scope * > .ranking-card');
        let res = [];
        for (const c of cards) {
            res.push('=== CARD: ' + c.querySelector('.card-header')?.textContent.trim());
            const items = c.querySelectorAll('[class*=ranking-item], [class*=rank-item]');
            res.push('ITEM_COUNT=' + items.length);
            for (const it of [...items].slice(0, 2)) res.push(it.outerHTML);
        }
        // 卡片顺序全景
        res.push('=== SIDEBAR CHILDREN ===');
        for (const ch of sidebar.children) {
            res.push('<' + ch.tagName.toLowerCase() + ' class="' + ch.className + '"> ' +
                (ch.textContent || '').trim().slice(0, 30));
        }
        return res.join('\\n\\n');
    }""")
    print(out[:6000])
    b.close()
