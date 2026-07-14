/**
 * Lulu Ads client. Guarantees enforced in code: never throws, hard timeout
 * (default 150ms), label always "Sponsored", context keys allowlisted.
 * Ships data, never directives — the host decides whether to render.
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
}

const ALLOWED_CONTEXT_KEYS = new Set(["tool", "category", "query", "route", "locale", "country"]);
const MAX_VALUE_LEN = 200;

function cleanContext(context?: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(context ?? {})) {
    if (ALLOWED_CONTEXT_KEYS.has(k) && v != null) out[k] = String(v).slice(0, MAX_VALUE_LEN);
  }
  return out;
}

export class LuluAds {
  private publisherId?: string;
  private apiKey?: string;
  private baseUrl: string;

  constructor(opts?: { publisherId?: string; apiKey?: string; baseUrl?: string }) {
    this.publisherId = opts?.publisherId ?? process.env.LULU_ADS_PUBLISHER_ID;
    this.apiKey = opts?.apiKey ?? process.env.LULU_ADS_API_KEY;
    const baseUrl = opts?.baseUrl ?? process.env.LULU_ADS_BASE_URL ?? "https://ads.getlulu.dev";
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private isInert(): boolean {
    return !this.publisherId || !this.apiKey;
  }

  async sponsoredSlot(opts?: {
    context?: Record<string, unknown>;
    timeoutMs?: number;
  }): Promise<Sponsored | null> {
    if (this.isInert()) return null;

    try {
      const res = await fetch(`${this.baseUrl}/slot`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": this.apiKey! },
        body: JSON.stringify({ context: cleanContext(opts?.context) }),
        signal: AbortSignal.timeout(opts?.timeoutMs ?? 150),
      });
      if (res.status !== 200) return null;
      const body = (await res.json()) as { text?: unknown; url?: unknown };
      if (!body?.text || !body?.url) return null;
      return { label: "Sponsored", text: String(body.text), url: String(body.url) };
    } catch {
      return null;
    }
  }
}
