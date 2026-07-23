/**
 * Lulu Ads client. Guarantees enforced in code: never throws, hard timeout
 * (default 800ms, or 3000ms when the call implies server-side
 * classification -- see resolveTimeoutMs), label always "Sponsored",
 * context keys allowlisted. Ships data, never directives — the host
 * decides whether to render.
 *
 * 800ms isn't a round guess: load testing measured a steady 155-215ms
 * once the connection is warm against production ads.getlulu.dev; 800ms
 * is that floor plus real margin for slower network paths and a cold
 * first connection. The higher 3000ms only applies when ads-server may
 * run its own server-side Gemini classification call (see
 * ads-server/app/classify.py) -- see resolveTimeoutMs below.
 *
 * Credentials resolve from opts first, then env vars
 * (LULU_ADS_PUBLISHER_ID, LULU_ADS_API_KEY, LULU_ADS_BASE_URL). If
 * publisherId or apiKey end up missing, the client is inert:
 * sponsoredSlot resolves null immediately with no fetch call.
 */
export interface Sponsored {
  label: "Sponsored";
  text: string;
  url: string;
  logoUrl?: string;
}

const ALLOWED_CONTEXT_KEYS = new Set(["tool", "category", "query", "route", "locale", "country", "prompt"]);
const MAX_VALUE_LEN = 200;
// ads-server only classifies server-side (a real Gemini call on its own
// 2.0s internal budget, see ads-server/app/classify.py) when "category" is
// absent AND "prompt" is present -- an explicit category always
// short-circuits classification. So the timeout is conditional on which
// path a given call actually takes, rather than one flat number sized for
// the slowest case: a category-only or context-free call never touches
// Gemini server-side and shouldn't eat a 3s ceiling just because *some*
// calls do.
//
// FAST_TIMEOUT_MS covers matching + network only. 150ms was already broken
// for a cold connection alone (measured 2.46s cold vs ~150ms warm against
// ads-server in production); 800ms clears a cold connection with real
// margin while staying tight enough that a slow ads-server can't visibly
// stall the caller's own tool call.
//
// CLASSIFY_TIMEOUT_MS covers matching + network + the server-side Gemini
// hop, and only applies when that hop is actually going to run.
const FAST_TIMEOUT_MS = 800;
const CLASSIFY_TIMEOUT_MS = 3000;
const DEFAULT_CACHE_TTL_MS = 45_000;

function resolveTimeoutMs(context: Record<string, unknown> | undefined, timeoutMs: number | undefined): number {
  if (timeoutMs != null) return timeoutMs;
  if (context?.prompt && !context?.category) return CLASSIFY_TIMEOUT_MS;
  return FAST_TIMEOUT_MS;
}

function cleanContext(context?: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(context ?? {})) {
    if (ALLOWED_CONTEXT_KEYS.has(k) && v != null) out[k] = String(v).slice(0, MAX_VALUE_LEN);
  }
  return out;
}

// Non-cryptographic (FNV-1a) — this is a cache key, not a security
// boundary, and avoiding node:crypto keeps the client portable to
// non-Node runtimes (edge/workers) that also have global fetch.
function hashString(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16);
}

function computeCacheKey(cleaned: Record<string, string>): string | null {
  // See client.py's _cache_key for the full rationale (category first,
  // prompt hash as fallback, no caching without either).
  if (cleaned.category) return `cat:${cleaned.category}`;
  if (cleaned.prompt) return `prompt:${hashString(cleaned.prompt)}`;
  return null;
}

/**
 * formatSuffix(sponsored) — for runtimes that OWN the final response surface
 * (chat bots, WhatsApp/Telegram agents, self-hosted assistants). The HARNESS
 * appends this to the model's output as deterministic code, after generation
 * — never as a model instruction. Returns "" for null/undefined/missing
 * fields so callers can always safely concatenate.
 */
export function formatSuffix(sponsored: Sponsored | null | undefined): string {
  if (!sponsored?.text || !sponsored?.url) return "";
  return `\n\n— Sponsored: ${sponsored.text} → ${sponsored.url}`;
}

export class LuluAds {
  private publisherId?: string;
  private apiKey?: string;
  private baseUrl: string;
  private cacheTtlMs: number;
  private cache = new Map<string, { value: Sponsored; expiresAt: number }>();

  constructor(opts?: { publisherId?: string; apiKey?: string; baseUrl?: string; cacheTtlMs?: number }) {
    this.publisherId = opts?.publisherId ?? process.env.LULU_ADS_PUBLISHER_ID;
    this.apiKey = opts?.apiKey ?? process.env.LULU_ADS_API_KEY;
    const baseUrl = opts?.baseUrl ?? process.env.LULU_ADS_BASE_URL ?? "https://ads.getlulu.dev";
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.cacheTtlMs = opts?.cacheTtlMs ?? DEFAULT_CACHE_TTL_MS;
  }

  private isInert(): boolean {
    return !this.publisherId || !this.apiKey;
  }

  async sponsoredSlot(opts?: {
    context?: Record<string, unknown>;
    timeoutMs?: number;
    /**
     * On/off switch for integrators running tiered pricing (a paid tier
     * that's ad-free, a free/discounted tier that carries ads). Pass
     * `enabled: false` and this resolves immediately with no fetch call,
     * same as missing credentials. Your own subscription/tier check
     * decides the value; defaults to true so existing callers are
     * unaffected.
     */
    enabled?: boolean;
  }): Promise<Sponsored | null> {
    if (opts?.enabled === false) return null;
    if (this.isInert()) return null;

    const cleaned = cleanContext(opts?.context);
    const key = computeCacheKey(cleaned);
    if (key) {
      const hit = this.cache.get(key);
      if (hit && hit.expiresAt > Date.now()) return hit.value;
    }

    try {
      const res = await fetch(`${this.baseUrl}/slot`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": this.apiKey! },
        body: JSON.stringify({ context: cleaned }),
        signal: AbortSignal.timeout(resolveTimeoutMs(opts?.context, opts?.timeoutMs)),
      });
      if (res.status !== 200) return null;
      const body = (await res.json()) as { text?: unknown; url?: unknown; logo_url?: unknown };
      if (!body?.text || !body?.url) return null;
      const result: Sponsored = { label: "Sponsored", text: String(body.text), url: String(body.url) };
      if (body.logo_url) result.logoUrl = String(body.logo_url);
      if (key) this.cache.set(key, { value: result, expiresAt: Date.now() + this.cacheTtlMs });
      return result;
    } catch {
      return null;
    }
  }

  /**
   * Best-effort: pings ads-server's /health to pre-establish a warm
   * connection before any real sponsoredSlot call happens. Not called
   * automatically -- a real network request as a side effect of the
   * constructor is surprising and untestable. Call this once yourself, at
   * your own process startup (fire-and-forget, no need to await):
   *
   *   const client = new LuluAds({...});
   *   client.warmUp();
   *
   * A slot request is often the first outbound call an integrator's
   * process makes; the first request on a cold connection can take
   * seconds (see DEFAULT_TIMEOUT_MS's comment). Never throws.
   */
  async warmUp(): Promise<void> {
    try {
      await fetch(`${this.baseUrl}/health`, { signal: AbortSignal.timeout(5000) });
    } catch {
      // best-effort
    }
  }
}

export { withLuluAds } from "./mcp.js";
export { formatCliCard, isCliClient, KNOWN_CLI_CLIENTS } from "./cliCard.js";
