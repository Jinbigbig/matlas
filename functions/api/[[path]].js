// Matlas 边缘实时接口：从 Cloudflare KV 读取本地采集器推送的 JSON 快照。
// 覆盖本地 live_server 的全部端点，域名与路径不变，前端零改动。
//   /api/health                  服务状态
//   /api/dates                   可用日期
//   /api/live?date=YYYY-MM-DD    当日实时数据
//   /api/live?date=...&light=1   轻量版（比赛列表用）
//   /api/live/<match_id>         单场数据
// KV key：live/<date>.json  light/<date>.json  index.json
// 回退：KV 拿不到（如免费版当日写入配额耗尽）时读同站静态快照
//       data/live/<date>.json / light-<date>.json / index.json

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "*",
    },
  });
}

// 同时取 KV 与静态快照，按 updated 取较新的一份。
// KV 配额耗尽时它停在最后一次成功写入的时刻，此时部署上来的静态快照更新。
async function readJson(env, origin, kvKey, staticPath) {
  const kv = await env.MATLAS_KV.get(kvKey, "json").catch(() => null);
  let snap = null;
  if (staticPath) {
    try {
      const res = await env.ASSETS.fetch(new URL(staticPath, origin));
      if (res.ok) snap = await res.json();
    } catch (e) {
      /* 静态快照缺失时只用 KV */
    }
  }
  if (kv && snap) {
    // updated 为 "YYYY-MM-DD HH:MM:SS"，同格式可直接按字符串比较
    return String(snap.updated || "") >= String(kv.updated || "") ? snap : kv;
  }
  return kv || snap || null;
}

export async function onRequestGet(context) {
  const { env, request } = context;
  const url = new URL(request.url);
  const path = url.pathname;
  const origin = url.origin;

  if (path === "/api/health") {
    const idx = await readJson(env, origin, "index.json", "/data/live/index.json");
    return json({
      ok: true,
      now: new Date().toISOString(),
      source: "cf-kv",
      dates: idx && idx.dates ? idx.dates.length : 0,
      updated: idx && idx.updated ? idx.updated : "",
    });
  }

  if (path === "/api/dates") {
    const idx = await readJson(env, origin, "index.json", "/data/live/index.json");
    return json({ dates: (idx && idx.dates) || [] });
  }

  if (path === "/api/live") {
    let date = url.searchParams.get("date") || "";
    const light = ["1", "true", "yes"].includes(url.searchParams.get("light"));
    if (!date) {
      const idx = await readJson(env, origin, "index.json", "/data/live/index.json");
      date = idx && idx.dates && idx.dates.length ? idx.dates[idx.dates.length - 1] : "";
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return json({ error: "bad date" }, 400);
    const key = (light ? "light/" : "live/") + date + ".json";
    const snap = "/data/live/" + (light ? "light-" : "") + date + ".json";
    const obj = await readJson(env, origin, key, snap);
    return obj ? json(obj) : json({ error: "no data for " + date }, 404);
  }

  if (path.startsWith("/api/live/")) {
    const mid = decodeURIComponent(path.slice("/api/live/".length));
    const date = mid.slice(0, 10);
    const obj = await readJson(env, origin, "live/" + date + ".json",
                               "/data/live/" + date + ".json");
    if (obj && obj.matches) {
      const hit = obj.matches.find((m) => m.match_id === mid);
      if (hit) return json({ date, match: hit });
    }
    return json({ error: "no match " + mid }, 404);
  }

  return json({ error: "not found" }, 404);
}

export async function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
    },
  });
}
