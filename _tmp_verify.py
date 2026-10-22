# 验证：SVG 顶导 / 球队Top / 徽章 / 宽度 / 回顶部 / 文字已删
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto("http://127.0.0.1:8799/index.html")
    pg.wait_for_load_state("networkidle")

    # 宽度复核
    w = pg.evaluate("""() => ({
        mainCol: document.querySelector('.v4-main-col').getBoundingClientRect().width,
        side: document.querySelector('.right-sidebar-new').getBoundingClientRect().width,
    })""")
    print("宽度:", w)

    # 已删文字检查
    txt = pg.evaluate("() => document.body.innerText")
    for bad in ("示例数据：对阵", "本站仅提供赛事前瞻", "结构化量化数据与结论，含"):
        print("残留" if bad in txt else "已删:", bad)

    # 顶导 SVG 数
    print("顶导SVG:", pg.evaluate("() => document.querySelectorAll('nav.site svg').length"))

    # 侧栏卡数
    print("侧栏卡:", pg.evaluate(
        "() => [...document.querySelectorAll('.right-sidebar-new .card-header')].map(e=>e.textContent)"))

    # 回顶部：滚到底
    pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    pg.wait_for_timeout(400)
    print("回顶部可见:", pg.evaluate(
        "() => getComputedStyle(document.getElementById('back-top')).display"))
    pg.screenshot(path="C:/tmp/v5_bottom.png")

    pg.evaluate("window.scrollTo(0, 0)")
    pg.wait_for_timeout(400)
    pg.screenshot(path="C:/tmp/v5_home.png", full_page=False)
    b.close()
print("ok")
