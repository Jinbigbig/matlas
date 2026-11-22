// Matlas 边缘实时接口：从 Cloudflare KV 读取本地采集器推送的 JSON 快照。
// 覆盖本地 live_server 的全部端点，域名与路径不变，前端零改动。
//   /api/health                  服务状态
//   /api/dates                   可用日期
//   /api/live?date=YYYY-MM-DD    当日实时数据
//   /api/live?date=...&light=1   轻量版（比赛列表用）
//   /api/live/<match_id>         单场数据
// KV key：live/<date>.json  light/<date>.json  index.json
// 数据统一（2026-11-22）：静态快照只维护 GH 一份（gh-pages data/live/），
// 本接口只读 KV；KV 不可达时返回 404，前端跨域读 GH 那份兜底，不在 CF 另存静态。

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

// 只读 KV：静态快照统一由 GH 那份维护，CF 不再读同站静态兜底。
// KV 配额耗尽时返回 null，前端按 updated 择新时会跨域取 GH 静态。
async function readJson(env, kvKey) {
  return await env.MATLAS_KV.get(kvKey, "json").catch(() => null);
}

export async function onRequestGet(context) {
  const { env, request } = context;
  const url = new URL(request.url);
  const path = url.pathname;

  if (path === "/api/health") {
    const idx = await readJson(env, "index.json");
    return json({
      ok: true,
      now: new Date().toISOString(),
      source: "cf-kv",
      dates: idx && idx.dates ? idx.dates.length : 0,
      updated: idx && idx.updated ? idx.updated : "",
    });
  }

  if (path === "/api/dates") {
    const idx = await readJson(env, "index.json");
    return json({ dates: (idx && idx.dates) || [] });
  }

  if (path === "/api/live") {
    let date = url.searchParams.get("date") || "";
    const light = ["1", "true", "yes"].includes(url.searchParams.get("light"));
    if (!date) {
      const idx = await readJson(env, "index.json");
      date = idx && idx.dates && idx.dates.length ? idx.dates[idx.dates.length - 1] : "";
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return json({ error: "bad date" }, 400);
    const key = (light ? "light/" : "live/") + date + ".json";
    const obj = await readJson(env, key);
    return obj ? json(obj) : json({ error: "no data for " + date }, 404);
  }

  if (path.startsWith("/api/live/")) {
    const mid = decodeURIComponent(path.slice("/api/live/".length));
    const date = mid.slice(0, 10);
    const obj = await readJson(env, "live/" + date + ".json");
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
