import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { LuluAds, formatSuffix } from "../src/index.js";

const GOOD = { label: "Sponsored", text: "Lulu Ads", url: "https://ads.getlulu.dev/c/x" };

function mockFetch(impl: typeof fetch) {
  vi.stubGlobal("fetch", impl);
}

afterEach(() => vi.unstubAllGlobals());

function ads() {
  return new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" });
}

test("happy path", async () => {
  mockFetch(async (url, init) => {
    expect(String(url)).toBe("https://ads.getlulu.dev/slot");
    expect((init!.headers as Record<string, string>)["x-api-key"]).toBe("lk_x");
    expect(JSON.parse(init!.body as string).context).toEqual({ tool: "search_flights" });
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  expect(await ads().sponsoredSlot({ context: { tool: "search_flights" } })).toEqual(GOOD);
});

test("204 → null", async () => {
  mockFetch(async () => new Response(null, { status: 204 }));
  expect(await ads().sponsoredSlot({ context: { tool: "x" } })).toBeNull();
});

test("500 → null", async () => {
  mockFetch(async () => new Response("boom", { status: 500 }));
  expect(await ads().sponsoredSlot({})).toBeNull();
});

test("network error → null", async () => {
  mockFetch(async () => { throw new TypeError("fetch failed"); });
  expect(await ads().sponsoredSlot({})).toBeNull();
});

test("timeout → null", async () => {
  mockFetch((_url, init) => new Promise((_resolve, reject) => {
    init!.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  }) as Promise<Response>);
  expect(await ads().sponsoredSlot({ timeoutMs: 30 })).toBeNull();
});

test("label forced to Sponsored", async () => {
  mockFetch(async () => new Response(JSON.stringify({ label: "Ad", text: "t", url: "https://u" }), { status: 200 }));
  expect((await ads().sponsoredSlot({}))!.label).toBe("Sponsored");
});

test("context keys allowlisted", async () => {
  let captured: Record<string, unknown> = {};
  mockFetch(async (_url, init) => {
    captured = JSON.parse(init!.body as string).context;
    return new Response(null, { status: 204 });
  });
  await ads().sponsoredSlot({ context: { tool: "x", user_email: "a@b.c" } });
  expect(captured).toEqual({ tool: "x" });
});

const ENV_KEYS = ["LULU_ADS_PUBLISHER_ID", "LULU_ADS_API_KEY", "LULU_ADS_BASE_URL"] as const;
let savedEnv: Record<string, string | undefined> = {};

beforeEach(() => {
  savedEnv = {};
  for (const k of ENV_KEYS) savedEnv[k] = process.env[k];
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (savedEnv[k] === undefined) delete process.env[k];
    else process.env[k] = savedEnv[k];
  }
});

test("no opts, no env → inert, resolves null, no fetch call", async () => {
  for (const k of ENV_KEYS) delete process.env[k];
  const fetchSpy = vi.fn();
  mockFetch(fetchSpy as unknown as typeof fetch);
  const result = await new LuluAds().sponsoredSlot({ context: { tool: "x" } });
  expect(result).toBeNull();
  expect(fetchSpy).not.toHaveBeenCalled();
});

test("formatSuffix: null/undefined → empty string", () => {
  expect(formatSuffix(null)).toBe("");
  expect(formatSuffix(undefined)).toBe("");
});

test("formatSuffix: happy path contains Sponsored, text, url", () => {
  const suffix = formatSuffix(GOOD);
  expect(suffix).toContain("Sponsored:");
  expect(suffix).toContain(GOOD.text);
  expect(suffix).toContain(GOOD.url);
});

test("env vars set → used as defaults, x-api-key from env", async () => {
  process.env.LULU_ADS_PUBLISHER_ID = "pub_env";
  process.env.LULU_ADS_API_KEY = "lk_env_key";
  delete process.env.LULU_ADS_BASE_URL;
  mockFetch(async (url, init) => {
    expect(String(url)).toBe("https://ads.getlulu.dev/slot");
    expect((init!.headers as Record<string, string>)["x-api-key"]).toBe("lk_env_key");
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  expect(await new LuluAds().sponsoredSlot({ context: { tool: "x" } })).toEqual(GOOD);
});

test("prompt passes through the context allowlist", async () => {
  mockFetch(async (_url, init) => {
    expect(JSON.parse(init!.body as string).context).toEqual({ prompt: "best flights to paris" });
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  expect(await ads().sponsoredSlot({ context: { prompt: "best flights to paris" } })).toEqual(GOOD);
});

test("logoUrl present when the response has one", async () => {
  mockFetch(async () => new Response(JSON.stringify({ ...GOOD, logo_url: "https://example.com/logo.png" }), { status: 200 }));
  const out = await ads().sponsoredSlot({ context: { tool: "x" } });
  expect(out?.logoUrl).toBe("https://example.com/logo.png");
});

test("logoUrl absent when the response has none", async () => {
  mockFetch(async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const out = await ads().sponsoredSlot({ context: { tool: "x" } });
  expect(out).not.toHaveProperty("logoUrl");
});

test("fast default times out without prompt", async () => {
  mockFetch((_url, init) => new Promise((_resolve, reject) => {
    setTimeout(() => reject(new DOMException("aborted", "AbortError")), 1000);
    init!.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  }) as Promise<Response>);
  const start = Date.now();
  const out = await ads().sponsoredSlot({ context: { tool: "x" } });
  expect(out).toBeNull();
  expect(Date.now() - start).toBeLessThan(1000);
});

test("classify default survives prompt without category", async () => {
  mockFetch(async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const out = await ads().sponsoredSlot({ context: { prompt: "best flights to paris" } });
  expect(out).toEqual(GOOD);
});

test("fast default applies even with prompt when category explicit", async () => {
  mockFetch((_url, init) => new Promise((_resolve, reject) => {
    init!.signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  }) as Promise<Response>);
  const start = Date.now();
  const out = await ads().sponsoredSlot({ context: { category: "travel.flights", prompt: "best flights to paris" } });
  expect(out).toBeNull();
  expect(Date.now() - start).toBeLessThan(1000);
});

test("enabled: false skips with no fetch call", async () => {
  const fetchSpy = vi.fn();
  mockFetch(fetchSpy as unknown as typeof fetch);
  const out = await ads().sponsoredSlot({ context: { tool: "x" }, enabled: false });
  expect(out).toBeNull();
  expect(fetchSpy).not.toHaveBeenCalled();
});

test("enabled defaults to true", async () => {
  mockFetch(async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  expect(await ads().sponsoredSlot({ context: { tool: "x" } })).toEqual(GOOD);
});

test("warmUp hits /health and /telemetry/init and never throws on failure", async () => {
  const calls: string[] = [];
  mockFetch(async (url) => {
    calls.push(String(url));
    throw new TypeError("network down");
  });
  await expect(ads().warmUp()).resolves.toBeUndefined();
  expect(calls).toEqual(["https://ads.getlulu.dev/health", "https://ads.getlulu.dev/telemetry/init"]);
});

test("warmUp's /telemetry/init call carries the x-api-key header", async () => {
  let capturedHeaders: Record<string, string> | undefined;
  mockFetch(async (url, init) => {
    if (String(url).includes("/telemetry/init")) {
      capturedHeaders = init?.headers as Record<string, string>;
    }
    return new Response("ok");
  });
  await ads().warmUp();
  expect(capturedHeaders?.["x-api-key"]).toBe("lk_x");
});

// ── short-TTL cache ────────────────────────────────────────────────────

test("cache hit within TTL skips fetch", async () => {
  let calls = 0;
  mockFetch(async () => {
    calls++;
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  const client = ads();
  const first = await client.sponsoredSlot({ context: { category: "travel.flights" } });
  const second = await client.sponsoredSlot({ context: { category: "travel.flights" } });
  expect(first).toEqual(GOOD);
  expect(second).toEqual(GOOD);
  expect(calls).toBe(1);
});

test("cache expires after TTL", async () => {
  let calls = 0;
  mockFetch(async () => {
    calls++;
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  const client = new LuluAds({ publisherId: "pub_1", apiKey: "lk_x", cacheTtlMs: 10 });
  await client.sponsoredSlot({ context: { category: "travel.flights" } });
  await new Promise((r) => setTimeout(r, 50));
  await client.sponsoredSlot({ context: { category: "travel.flights" } });
  expect(calls).toBe(2);
});

test("failure is never cached", async () => {
  let call = 0;
  mockFetch(async () => {
    call++;
    return call === 1
      ? new Response("boom", { status: 500 })
      : new Response(JSON.stringify(GOOD), { status: 200 });
  });
  const client = ads();
  const first = await client.sponsoredSlot({ context: { category: "travel.flights" } });
  const second = await client.sponsoredSlot({ context: { category: "travel.flights" } });
  expect(first).toBeNull();
  expect(second).toEqual(GOOD);
});

test("cache keys on prompt hash when no category", async () => {
  let calls = 0;
  mockFetch(async () => {
    calls++;
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  const client = ads();
  await client.sponsoredSlot({ context: { prompt: "best flights to paris" } });
  await client.sponsoredSlot({ context: { prompt: "best flights to paris" } });
  await client.sponsoredSlot({ context: { prompt: "a totally different prompt" } });
  expect(calls).toBe(2);
});

test("no category or prompt never caches", async () => {
  let calls = 0;
  mockFetch(async () => {
    calls++;
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  const client = ads();
  await client.sponsoredSlot({ context: { tool: "search_flights" } });
  await client.sponsoredSlot({ context: { tool: "search_flights" } });
  expect(calls).toBe(2);
});
