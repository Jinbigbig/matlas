# 定位侧栏两块 Top10 卡的真实 class 结构
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto("https://www.qiuxiaoce.com/", wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_timeout(2500)
    # 从「赛事Top 10」文本节点向上找 3 层，输出每层 class
    info = pg.evaluate("""() => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node, out = [];
        while ((node = walker.nextNode())) {
            if (node.textContent.includes('赛事Top 10')) {
                let e = node.parentElement;
                for (let i = 0; i < 4 && e; i++, e = e.parentElement) {
                    out.push('L' + i + ': <' + e.tagName.toLowerCase() + ' class="' + e.className + '">');
                }
                // 该卡内第一项的完整 HTML
                let card = node.parentElement;
                while (card && !card.textContent.includes('球队Top 10')) card = card.parentElement;
                if (card) {
                    out.push('CARD_CLASS=' + card.className);
                    const item = card.querySelector('[class*=item], [class*=rank]');
                    if (item) out.push('ITEM=' + item.outerHTML);
                    const head = node.parentElement.outerHTML;
                    out.push('HEAD=' + head);
                }
                break;
            }
        }
        return out.join('\\n');
    }""")
    print(info)
    b.close()
