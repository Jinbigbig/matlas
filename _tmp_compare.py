# 对照检查：抓 qiuxiaoce 与本站首页全页截图（桌面+移动）
from playwright.sync_api import sync_playwright

SITES = [
    ("qxc", "https://www.qiuxiaoce.com/"),
    ("matlas", "http://127.0.0.1:8799/index.html"),
]

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    for tag, url in SITES:
        d = b.new_page(viewport={"width": 1280, "height": 900})
        d.goto(url, wait_until="domcontentloaded", timeout=30000)
        d.wait_for_timeout(2500)
        d.screenshot(path=f"C:/tmp/cmp_{tag}_desktop.png", full_page=True)
        m = b.new_page(viewport={"width": 390, "height": 844})
        m.goto(url, wait_until="domcontentloaded", timeout=30000)
        m.wait_for_timeout(2500)
        m.screenshot(path=f"C:/tmp/cmp_{tag}_mobile.png", full_page=True)
    b.close()
print("ok")
