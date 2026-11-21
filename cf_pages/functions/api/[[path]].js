// Matlas 边缘实时接口：从 Cloudflare KV 读取本地采集器推送的 JSON 快照。
// 覆盖本地 live_server 的全部端点，域名与路径不变，前端零改动。
//   /api/health                  服务状态
//   /api/dates                   可用日期
//   /api/live?date=YYYY-MM-DD    当日实时数据
//   /api/live?date=...&light=1   轻量版（比赛列表用）
//   /api/live/<match_id>         单场数据
// KV key：live/<date>.json  light/<date>.json  index.json

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

export async function onRequestGet(context) {
  const { env, request } = context;
  const url = new URL(request.url);
  const path = url.pathname;
  const store = env.MATLAS_KV;

  if (path === "/api/health") {
    const idx = await store.get("index.json", "json");
    return json({
      ok: true,
      now: new Date().toISOString(),
      source: "cf-kv",
      dates: idx && idx.dates ? idx.dates.length : 0,
      updated: idx && idx.updated ? idx.updated : "",
    });
  }

  if (path === "/api/dates") {
    const idx = await store.get("index.json", "json");
    return json({ dates: (idx && idx.dates) || [] });
  }

  if (path === "/api/live") {
    let date = url.searchParams.get("date") || "";
    const light = ["1", "true", "yes"].includes(url.searchParams.get("light"));
    if (!date) {
      const idx = await store.get("index.json", "json");
      date = idx && idx.dates && idx.dates.length ? idx.dates[idx.dates.length - 1] : "";
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return json({ error: "bad date" }, 400);
    const key = (light ? "light/" : "live/") + date + ".json";
    const obj = await store.get(key, "json");
    return obj ? json(obj) : json({ error: "no data for " + date }, 404);
  }

  if (path.startsWith("/api/live/")) {
    const mid = decodeURIComponent(path.slice("/api/live/".length));
    const date = mid.slice(0, 10);
    const obj = await store.get("live/" + date + ".json", "json");
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
