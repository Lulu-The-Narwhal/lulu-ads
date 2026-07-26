/**
 * MCP Apps postMessage bridge for the React-built sponsored widget.
 *
 * Ports the three behaviors the hand-written js/src/widget.ts's inline
 * <script> already implements and that Task 1 live-verified against a real
 * MCP host (Claude.ai) -- see progress.md's Task 1 entry:
 *
 *   1. Handshake: send `ui/notifications/initialized` on load (+ a 300ms
 *      fallback timer so a missed `load` event can't deadlock the widget
 *      into permanently-hidden -- the host keeps the iframe reserved-but-
 *      hidden until this notification arrives).
 *   2. Listen for `ui/notifications/tool-result` and extract the
 *      `sponsored` payload from `msg.params.structuredContent.sponsored`
 *      -- the exact path Task 1 confirmed live, not the design doc's
 *      unverified sketch.
 *   3. Click redirect: route CTA clicks through `ui/open-link` (a real
 *      JSON-RPC request the host handles outside the sandbox) instead of a
 *      plain navigation, which gets silently swallowed inside the
 *      sandboxed iframe (no allow-popups).
 *
 * Deliberately NOT ported: re-sending `ui/notifications/size-changed` on
 * every incoming message. Task 1 live-tested that and it broke rendering.
 * `size-changed` is sent at most twice, each guarded to fire exactly
 * once: once as part of the initial handshake (measuring the skeleton),
 * and once more on the loading->settled transition (measuring the real
 * `loaded`/`noFill` card, which has a different height) -- see
 * `notifySizeChanged` and its call site in App.tsx. That is not the
 * "every incoming message" pattern Task 1 found broken.
 */

/** Parsed shape SponsoredCard's "loaded" state needs. `cta` isn't part of
 * the wire payload (structuredContent.sponsored only carries
 * {label,text,url,logo_url}, confirmed live by Task 1) -- it's a
 * widget-level constant, same default `sponsoredWidgetHtml()` already
 * uses today. */
export interface SponsoredData {
  label: string
  text: string
  url: string
  logoDataUri?: string
  cta: string
}

const DEFAULT_CTA = "Learn more →"
const TOOL_RESULT_METHOD = "ui/notifications/tool-result"
const OPTS_ELEMENT_ID = "lulu-ads-opts"

/**
 * Registration-time defaults `sponsoredWidgetHtml()` (js/src/widget.ts)
 * bakes into the compiled bundle's `#lulu-ads-opts[data-opts]` attribute --
 * see `index.html`'s `__LULU_ADS_OPTS__` placeholder for the substitution
 * mechanism. `text`/`url`/`logoDataUri` are the registration-time "house
 * ad" content (unused at runtime once live `tool-result` data has taken
 * over -- kept here only because they're part of `SponsoredWidgetOptions`
 * and thus always present in the injected blob; a real per-call fallback
 * for hosts that never push `tool-result` is a real, currently-unaddressed
 * gap, not solved by reading these fields -- see the widget.ts docstring
 * and the task report). `label`/`cta`/`accent*` are genuinely used: they
 * become the defaults `extractSponsored` falls back to when the live
 * payload omits them (`label`, since the wire payload sometimes carries
 * one; `cta`, since it never does) and the static theme colors
 * `applyAccentTheme` applies once, outside the live-data path.
 */
export interface InitialOptions {
  text: string
  url: string
  label?: string
  cta?: string
  logoDataUri?: string
  accent?: string
  accentLight?: string
  accentDark?: string
}

/**
 * Reads and JSON-parses the per-call options baked into the compiled
 * bundle at `sponsoredWidgetHtml()` build/render time (see
 * `InitialOptions`'s doc). Returns `null` if the element is missing, its
 * `data-opts` attribute isn't valid JSON (e.g. running the unbuilt
 * `vite dev` source directly, where the `__LULU_ADS_OPTS__` placeholder is
 * never substituted), or the parsed value isn't an object -- callers must
 * treat `null` as "no baked defaults available," not as an error.
 * Reads via `getAttribute`, never `innerHTML`/`eval` -- the browser's own
 * HTML-attribute-value decoding is what makes the escaped JSON blob safe
 * to embed in the first place (see `index.html`'s comment on the element).
 */
export function readInitialOptions(): InitialOptions | null {
  const el = document.getElementById(OPTS_ELEMENT_ID)
  const raw = el?.getAttribute("data-opts")
  if (!raw) return null
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return null
    return parsed as InitialOptions
  } catch {
    return null
  }
}

/** Loose shape of the wire payload -- only what we read. Field names
 * mirror Task 1's confirmed live shape: {jsonrpc, method, params:
 * {content, isError, structuredContent:{...,sponsored:{label,text,url,
 * logo_url}}}}. `logoUrl` (camelCase) is also accepted defensively: the
 * compiled widget bundle is shared by both the JS and Python SDKs (see
 * design doc), and js/src/index.ts's `Sponsored` TS type currently
 * serializes that field as `logoUrl` while the Python client and Task 1's
 * live-confirmed payload both use `logo_url` -- an existing cross-SDK
 * naming inconsistency this bridge works around rather than silently
 * assumes away. */
interface RawSponsored {
  label?: unknown
  text?: unknown
  url?: unknown
  logo_url?: unknown
  logoUrl?: unknown
}

interface RawToolResultMessage {
  jsonrpc?: unknown
  method?: unknown
  params?: {
    structuredContent?: {
      sponsored?: RawSponsored
    }
  }
}

/** Extracts and validates the sponsored payload out of a raw
 * `ui/notifications/tool-result` message. Returns `null` for the no-fill
 * case (no `sponsored` field, or one missing required text/url) -- callers
 * must treat `null` as "render nothing," not as an error. */
export function extractSponsored(msg: RawToolResultMessage, defaults?: InitialOptions | null): SponsoredData | null {
  const sponsored = msg.params?.structuredContent?.sponsored
  if (!sponsored || typeof sponsored !== "object") return null

  const text = sponsored.text
  const url = sponsored.url
  if (typeof text !== "string" || typeof url !== "string" || !text || !url) return null

  const label =
    typeof sponsored.label === "string" && sponsored.label
      ? sponsored.label
      : (defaults?.label ?? "Sponsored")
  const logoDataUri =
    typeof sponsored.logo_url === "string" && sponsored.logo_url
      ? sponsored.logo_url
      : typeof sponsored.logoUrl === "string" && sponsored.logoUrl
        ? sponsored.logoUrl
        : undefined
  const cta = (defaults?.cta && defaults.cta.trim()) ? defaults.cta : DEFAULT_CTA

  return { label, text, url, logoDataUri, cta }
}

function isJsonRpcMessage(data: unknown): data is RawToolResultMessage {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as { jsonrpc?: unknown }).jsonrpc === "2.0" &&
    typeof (data as { method?: unknown }).method === "string"
  )
}

/**
 * Subscribes to `ui/notifications/tool-result` messages from the MCP host.
 * `onResult` fires with the parsed sponsored data, or `null` for the
 * no-fill case -- exactly once per tool-result message. Any other
 * `message` event (wrong jsonrpc version, unrelated method, non-MCP
 * postMessage noise) is ignored: `onResult` does not fire at all for
 * those, it does not fire with `null` as a stand-in for "irrelevant".
 *
 * `defaults` (typically `readInitialOptions()`'s result) is forwarded to
 * `extractSponsored` for its `label`/`cta` fallback -- see that function's
 * doc.
 *
 * Returns an unsubscribe function.
 */
export function listenForToolResult(
  onResult: (sponsored: SponsoredData | null) => void,
  defaults?: InitialOptions | null
): () => void {
  function handleMessage(event: MessageEvent) {
    const msg = event.data
    if (!isJsonRpcMessage(msg)) return
    if (msg.method !== TOOL_RESULT_METHOD) return
    onResult(extractSponsored(msg, defaults))
  }
  window.addEventListener("message", handleMessage)
  return () => window.removeEventListener("message", handleMessage)
}

/**
 * Measures the current document height and posts a single
 * `ui/notifications/size-changed` to the host. Shared by `initHandshake`
 * (measures the initial skeleton) and the one-time loading->settled resend
 * App.tsx triggers once real tool-result data swaps the skeleton for the
 * `loaded`/`noFill` card -- see the module docstring. No-ops if the
 * measured height is falsy (e.g. unlaid-out in a test environment).
 */
export function notifySizeChanged(): void {
  const h = document.body.scrollHeight
  if (h) {
    window.parent.postMessage(
      { jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { width: 400, height: h } },
      "*"
    )
  }
}

/**
 * MCP Apps handshake: sends `ui/notifications/initialized` once the page
 * has loaded (or immediately if it already has, plus a 300ms fallback
 * timer in case the `load` event was already missed). Also sends one
 * `ui/notifications/size-changed` alongside it (via `notifySizeChanged`),
 * matching the original -- this fires once here, never again on
 * subsequent messages (the one exception being the single loading->settled
 * resend App.tsx triggers separately, see `notifySizeChanged`'s doc).
 */
export function initHandshake(): void {
  let sent = false
  function notifyInitialized() {
    if (sent) return
    sent = true
    window.parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} }, "*")
    notifySizeChanged()
  }
  if (document.readyState === "complete") {
    notifyInitialized()
  } else {
    window.addEventListener("load", notifyInitialized)
  }
  setTimeout(notifyInitialized, 300)
}

/** Sends a `ui/open-link` request to the host instead of a plain
 * navigation -- see the module docstring for why. `id` just needs to be
 * unique per request; nothing currently reads the response. */
export function openLink(url: string): void {
  window.parent.postMessage(
    { jsonrpc: "2.0", id: `open-link-${Date.now()}`, method: "ui/open-link", params: { url } },
    "*"
  )
}

/**
 * Delegated click handler for CTA elements: any click landing on (or
 * inside) an element carrying `data-url` is redirected through
 * `openLink()` instead of following a plain href/button click.
 * `SponsoredCard`'s CTA button already carries `data-url={url}` (see
 * SponsoredCard.tsx) -- delegation here means this works regardless of
 * whether that CTA is a <button> (current Base UI shadcn component) or a
 * future <a>, and regardless of when React mounts/swaps it in, unlike the
 * original's one-time `querySelectorAll("a[href]")` pass over static HTML.
 *
 * Returns an unsubscribe function.
 */
export function initClickRedirect(): () => void {
  function handleClick(event: MouseEvent) {
    const target = event.target
    if (!(target instanceof Element)) return
    const urlEl = target.closest("[data-url]")
    if (!urlEl) return
    const url = urlEl.getAttribute("data-url")
    if (!url) return
    event.preventDefault()
    openLink(url)
  }
  document.addEventListener("click", handleClick)
  return () => document.removeEventListener("click", handleClick)
}

/**
 * Applies per-integrator brand colors (`SponsoredWidgetOptions.accent` /
 * `accentLight` / `accentDark`, baked into `InitialOptions` -- see
 * `readInitialOptions`) as CSS custom properties on the document root.
 * `SponsoredCard.tsx`'s gradient reads these via `var(--lulu-accent,
 * <hardcoded default>)`, so calling this with `null`/absent fields is a
 * no-op that leaves the hardcoded Lulu brand defaults in place -- this is
 * the mechanism that makes `accent*` overrides in `sponsoredWidgetHtml()`
 * actually reach the compiled bundle (previously a real gap: the React
 * component only ever rendered the hardcoded constants, ignoring any
 * `accent*` option). Applied once, outside the live `tool-result` path --
 * these are static per-widget-instance theme values, never sent over the
 * wire per call.
 */
export function applyAccentTheme(opts?: InitialOptions | null): void {
  if (!opts) return
  const root = document.documentElement
  if (opts.accent) root.style.setProperty("--lulu-accent", opts.accent)
  if (opts.accentLight) root.style.setProperty("--lulu-accent-light", opts.accentLight)
  if (opts.accentDark) root.style.setProperty("--lulu-accent-dark", opts.accentDark)
}
