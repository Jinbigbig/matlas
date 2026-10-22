# 收集对方联赛徽章映射：从 sitemap 找 league-topic 页，逐页抓 alt/src 对
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")

# 1. sitemap
sm = None
for cand in ("https://www.qiuxiaoce.com/wp-sitemap.xml", "https://www.qiuxiaoce.com/sitemap.xml",
             "https://www.qiuxiaoce.com/sitemap_index.xml"):
    try:
        sm = get(cand)
        print("SITEMAP OK:", cand, len(sm))
        break
    except Exception as e:
        print("miss:", cand, str(e)[:60])

pairs = {}
if sm:
    subs = re.findall(r"<loc>([^<]+)</loc>", sm)
    print("sub sitemaps:", len(subs), subs[:6])
    # league-topic 页所在子 sitemap
    lt = [u for u in subs if "league" in u or "topic" in u]
    pages = []
    for u in lt or subs[:3]:
        try:
            body = get(u)
            pages += re.findall(r"<loc>([^<]+league-topic[^<]+)</loc>", body)
        except Exception:
            pass
    print("league-topic pages:", len(pages), pages[:5])
    for u in pages[:60]:
        try:
            h = get(u)
            for m in re.finditer(r'<img[^>]+src="([^"]*competitions/[^"]+)"[^>]*alt="([^"]*)"|<img[^>]+alt="([^"]*)"[^>]*src="([^"]*competitions/[^"]+)"', h):
                src = m.group(1) or m.group(4)
                alt = m.group(2) or m.group(3)
                if src and alt:
                    pairs[alt.strip()] = src
        except Exception as e:
            print("ERR", u, str(e)[:50])
print("pairs:", len(pairs))
import json
open("C:/tmp/qxc_league_logos.json", "w", encoding="utf-8").write(
    json.dumps(pairs, ensure_ascii=False, indent=1))
for k, v in list(pairs.items())[:20]:
    print(k, "->", v)
