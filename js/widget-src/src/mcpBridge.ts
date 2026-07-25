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
export function extractSponsored(msg: RawToolResultMessage): SponsoredData | null {
  const sponsored = msg.params?.structuredContent?.sponsored
  if (!sponsored || typeof sponsored !== "object") return null

  const text = sponsored.text
  const url = sponsored.url
  if (typeof text !== "string" || typeof url !== "string" || !text || !url) return null

  const label = typeof sponsored.label === "string" && sponsored.label ? sponsored.label : "Sponsored"
  const logoDataUri =
    typeof sponsored.logo_url === "string" && sponsored.logo_url
      ? sponsored.logo_url
      : typeof sponsored.logoUrl === "string" && sponsored.logoUrl
        ? sponsored.logoUrl
        : undefined

  return { label, text, url, logoDataUri, cta: DEFAULT_CTA }
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
 * Returns an unsubscribe function.
 */
export function listenForToolResult(onResult: (sponsored: SponsoredData | null) => void): () => void {
  function handleMessage(event: MessageEvent) {
    const msg = event.data
    if (!isJsonRpcMessage(msg)) return
    if (msg.method !== TOOL_RESULT_METHOD) return
    onResult(extractSponsored(msg))
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
