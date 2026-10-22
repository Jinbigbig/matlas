# 抓取 qiuxiaoce 首页主列头部结构（Tab/日期/筛选区），临时自检脚本
from playwright.sync_api import sync_playwright

JS = """() => {
    const scope = document.querySelector('.home-v4-scope');
    const main = scope ? scope.querySelector('.v4-main-col') : null;
    if (!main) return 'NO MAIN COL';
    const panel = main.querySelector('.v4-content-panel');
    let out = '';
    if (panel) {
        for (const child of panel.children) {
            if (child.classList.contains('match-card')) break;
            out += child.outerHTML + '\\n----\\n';
        }
    }
    // main 直接子元素全列（panel 之前的）
    const tops = [];
    for (const child of main.children) {
        if (child.classList.contains('v4-content-panel')) break;
        tops.push(child.outerHTML);
    }
    return tops.join('\\n=====TOP=====\\n') + '\\n=====PANEL_HEAD=====\\n' + out.slice(0, 8000);
}"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page()
    pg.goto("https://www.qiuxiaoce.com/", wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_timeout(2000)
    html = pg.evaluate(JS)
    with open("C:/tmp/qxc_mainhead.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(len(html))
    b.close()
