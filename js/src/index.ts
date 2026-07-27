/**
 * Lulu Ads client. Guarantees enforced in code: never throws, hard timeout
 * (default 1500ms, or 3000ms when the call implies server-side
 * classification -- see resolveTimeoutMs), label always "Sponsored",
 * context keys allowlisted. Ships data, never directives — the host
 * decides whether to render.
 *
 * 1500ms isn't a round guess: load testing once measured a steady
 * 155-215ms once the connection is warm against production
 * ads.getlulu.dev, but real production evidence (2026-07-26, via a live
 * third-party MCP server) directly contradicted that: calls this client
 * itself judged NOT cold still measured 796-802ms, right at the old 800ms
 * line rather than comfortably under it -- so 800ms had already stopped
 * being real margin. Raised to keep real margin over what's actually been
 * observed warm. The higher 3000ms only applies when ads-server may run
 * its own server-side Gemini classification call (see
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
// ads-server in production); 1500ms clears a cold connection with real
// margin while staying tight enough that a slow ads-server can't visibly
// stall the caller's own tool call. See this file's module docstring for
// why this isn't 800ms anymore.
//
// CLASSIFY_TIMEOUT_MS covers matching + network + the server-side Gemini
// hop, and only applies when that hop is actually going to run.
const FAST_TIMEOUT_MS = 1500;
const CLASSIFY_TIMEOUT_MS = 3000;
const DEFAULT_CACHE_TTL_MS = 45_000;

// Root cause of a real, reproducible 0% delivery rate discovered
// 2026-07-26: remote MCP hosts that reconnect per message (confirmed live:
// Claude.ai's connector opens a brand-new MCP session -- new TCP/TLS, new
// clientInfo/initialize handshake, different source IP -- for every single
// chat message, not once per conversation) mean the underlying HTTP
// connection this SDK's persistent client pools is cold far more often
// than "once at process start" -- the platform's default connection-pool
// idle eviction is on the order of seconds, far shorter than the real gap
// between two chat messages (a human reading and typing), so a fresh
// connection is the common case, not a one-time startup cost.
//
// First attempt at a fix (shipped, then found wrong on inspection): latch
// a per-client "have I ever succeeded" boolean and give ONLY the
// genuinely-first-ever call the larger budget. That's wrong the moment
// coldness recurs: call 1 succeeds with the extra headroom, the latch
// flips permanently true, and call 2 -- arriving after the very same kind
// of idle gap -- gets throttled back to the tight budget while facing an
// equally cold connection.
//
// Real fix: don't latch a boolean -- track WHEN this client last actually
// succeeded (a real sponsoredSlot response, or a warmUp() health check),
// and re-arm the larger budget any time that's more than
// KEEPALIVE_EXPIRY_MS ago (or never happened at all). A connection idle
// longer than that window is genuinely likely to need a fresh handshake,
// no matter how many prior calls succeeded; a connection used seconds ago
// is not, and a slow response on it is almost certainly the server, not
// the socket.
const COLD_START_TIMEOUT_MS = 3000;

// How long since this client's last real success before a connection is
// no longer trusted to still be warm. Mirrors client.py's
// _KEEPALIVE_EXPIRY_S -- keep both in sync, they hit the same backend.
const KEEPALIVE_EXPIRY_MS = 90_000;

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
  // Timestamp (ms since epoch) of this client's last real success (a
  // sponsoredSlot response or a warmUp() health check) -- null until the
  // first one. Read by isCold() to decide whether the NEXT call should get
  // COLD_START_TIMEOUT_MS's headroom. See COLD_START_TIMEOUT_MS's comment
  // for why this replaced a one-time "ever succeeded" boolean.
  private lastSuccessAt: number | null = null;

  private isCold(): boolean {
    return this.lastSuccessAt === null || Date.now() - this.lastSuccessAt > KEEPALIVE_EXPIRY_MS;
  }

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

    // Only when the caller didn't pass their own timeoutMs (an explicit
    // value is a deliberate choice, never second-guessed): if this
    // client's last real success was too long ago to trust the
    // connection is still warm (or there's never been one), give this
    // call real cold-connection headroom instead of the tight budget. See
    // COLD_START_TIMEOUT_MS's comment for why this is a per-call,
    // time-windowed check rather than a one-time latch.
    let effectiveTimeoutMs = resolveTimeoutMs(opts?.context, opts?.timeoutMs);
    if (opts?.timeoutMs == null && this.isCold()) {
      effectiveTimeoutMs = Math.max(effectiveTimeoutMs, COLD_START_TIMEOUT_MS);
    }

    try {
      const res = await fetch(`${this.baseUrl}/slot`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": this.apiKey! },
        body: JSON.stringify({ context: cleaned }),
        signal: AbortSignal.timeout(effectiveTimeoutMs),
      });
      if (res.status !== 200) return null;
      const body = (await res.json()) as { text?: unknown; url?: unknown; logo_url?: unknown };
      if (!body?.text || !body?.url) return null;
      const result: Sponsored = { label: "Sponsored", text: String(body.text), url: String(body.url) };
      if (body.logo_url) result.logoUrl = String(body.logo_url);
      this.lastSuccessAt = Date.now();
      if (key) this.cache.set(key, { value: result, expiresAt: Date.now() + this.cacheTtlMs });
      return result;
    } catch {
      return null;
    }
  }

  /**
   * Best-effort: pings ads-server's /health to pre-establish a warm
   * connection before any real sponsoredSlot call happens, and separately
   * reports this publisher's integration as alive via POST
   * /telemetry/init (fills the admin dashboard's "installed, not yet
   * serving" gap -- see lulu-platform's
   * 2026-07-24-lulu-ads-sdk-install-tracking-design.md). Not called
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
      const res = await fetch(`${this.baseUrl}/health`, { signal: AbortSignal.timeout(5000) });
      if (res.status === 200) this.lastSuccessAt = Date.now();
    } catch {
      // best-effort
    }
    try {
      await fetch(`${this.baseUrl}/telemetry/init`, {
        method: "POST",
        headers: { "x-api-key": this.apiKey ?? "" },
        signal: AbortSignal.timeout(5000),
      });
    } catch {
      // best-effort
    }
  }
}

export { withLuluAds, enableLuluAds } from "./mcp.js";
export { formatCliCard, isCliClient, KNOWN_CLI_CLIENTS } from "./cliCard.js";
