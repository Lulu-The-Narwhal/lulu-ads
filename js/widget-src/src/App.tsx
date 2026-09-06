import { useEffect, useRef, useState, type ReactNode } from "react"
import { Card } from "@/components/ui/card"
import { SponsoredCard, type SponsoredCardState, cardStyle } from "./SponsoredCard"
import { Banner } from "./Banner"
import { Footer } from "./Footer"

/**
 * Template registry (LUL-46): maps a `template` opt value to the component
 * rendering the card's INNER content for a given state. Every entry gets
 * the same persistent `<Card style={cardStyle}>` shell + `<Footer />`
 * wrapping it below (see App's render) -- the disclosed "Sponsored" label
 * lives inside each template component itself, but the outer gradient card
 * and "Powered by Lulu Ads" footer are structurally guaranteed by every
 * template, not something each one has to remember to add (LUL-45's
 * binding, non-negotiable contract).
 *
 * "card" (SponsoredCard) is the only entry today -- new templates land here
 * as their own components ship (LUL-47..57), never as a separate dispatch
 * mechanism. An unrecognized/missing `template` value falls back to "card"
 * rather than rendering nothing, matching widget.py/widget.ts's own
 * "unknown template" validation happening earlier, at registration time --
 * by the time this runs, a bad value already would have raised there, so
 * this fallback only ever matters for the unbuilt `vite dev` case (no
 * baked-in opts at all) or a bundle/SDK version mismatch.
 */
const TEMPLATES: Record<string, (props: { state: SponsoredCardState }) => ReactNode> = {
  card: SponsoredCard,
  banner: Banner,
}
import {
  applyAccentTheme,
  initClickRedirect,
  initHandshake,
  listenForToolResult,
  notifySizeChanged,
  readInitialOptions,
} from "./mcpBridge"

/**
 * The widget's React root. Starts in the skeleton state, then swaps to
 * `loaded`/`noFill` once the host's `ui/notifications/tool-result` message
 * for this call arrives -- see mcpBridge.ts for the message contract and
 * the ported handshake/click-redirect behaviors.
 *
 * Owns a single persistent `<Card style={cardStyle}>` shell -- the orange
 * gradient card -- that renders in every state (loading/loaded/noFill),
 * nesting both `<SponsoredCard>` (the swappable inner content: skeleton
 * bars, the loaded row, or nothing) and `<Footer />` inside it. This
 * matches the original hand-written widget's layout, where the footer sits
 * inside the card and inherits its cream-on-orange text color via normal
 * CSS inheritance -- see Footer.tsx.
 */
function App() {
  // Registration-time defaults baked into the compiled bundle by
  // sponsoredWidgetHtml() -- read once, synchronously, so applyAccentTheme
  // and the first listenForToolResult subscription both see the same
  // value the very first time they run (a plain DOM attribute read, not a
  // side effect, so doing it in the lazy useState initializer instead of
  // an effect is safe here -- this widget only ever renders client-side,
  // no SSR pass to worry about). `null` in `vite dev` (unbuilt source,
  // placeholder never substituted) or if the element/JSON is malformed --
  // see readInitialOptions's doc.
  const [initialOptions] = useState(() => readInitialOptions())
  const [state, setState] = useState<SponsoredCardState>({ kind: "loading" })
  const Content = TEMPLATES[initialOptions?.template ?? "card"] ?? SponsoredCard

  // Guards the one-time loading->settled size-changed resend below so it
  // fires exactly once for that transition, never again on later
  // re-renders (e.g. this component re-rendering for unrelated reasons
  // once already settled).
  const hasSentSettledSize = useRef(false)

  useEffect(() => {
    // Per-integrator brand colors (accent/accentLight/accentDark) --
    // static for the widget's lifetime, applied once, independent of
    // whatever live tool-result data later arrives.
    applyAccentTheme(initialOptions)

    // MCP Apps handshake -- must fire regardless of whether/when a
    // tool-result ever arrives, so the host un-hides the iframe at all.
    initHandshake()

    // CTA clicks (SponsoredCard's Button carries data-url={url}) redirect
    // through ui/open-link instead of a raw navigation, which the
    // sandboxed iframe would otherwise swallow.
    const unsubscribeClicks = initClickRedirect()

    const unsubscribeToolResult = listenForToolResult((sponsored) => {
      setState(sponsored ? { kind: "loaded", ...sponsored } : { kind: "noFill" })
    }, initialOptions)

    return () => {
      unsubscribeClicks()
      unsubscribeToolResult()
    }
  }, [initialOptions])

  // initHandshake() sends size-changed once, measuring whatever's
  // rendered at that moment (the skeleton). The skeleton and the settled
  // loaded/noFill card have different heights, so once the real
  // tool-result swaps state.kind away from "loading" for the first time,
  // resend size-changed once more so a real host doesn't keep the
  // skeleton's height reserved for the iframe. Runs after React commits
  // the new DOM (unlike calling this from inside the listenForToolResult
  // callback directly, which would measure the stale, pre-swap DOM).
  useEffect(() => {
    if (state.kind !== "loading" && !hasSentSettledSize.current) {
      hasSentSettledSize.current = true
      notifySizeChanged()
    }
  }, [state.kind])

  return (
    <Card
      className={
        "gap-0 rounded-[14px] border-0 p-3.5 px-4 py-3.5 ring-0" +
        (state.kind === "loaded" ? " card-shine" : "")
      }
      style={cardStyle}
      aria-busy={state.kind === "loading"}
      aria-label={state.kind === "loading" ? "Loading sponsored content" : undefined}
    >
      <Content state={state} />
      <Footer />
    </Card>
  )
}

export default App
