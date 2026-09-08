import { useEffect, useRef, useState, type ReactNode } from "react"
import { Card } from "@/components/ui/card"
import { SponsoredCard, type SponsoredCardState, cardStyle } from "./SponsoredCard"
import { Banner } from "./Banner"
import { FlipCard } from "./FlipCard"
import { ScratchReveal } from "./ScratchReveal"
import { Spin } from "./Spin"
import { Hero } from "./Hero"
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
 * rather than rendering nothing.
 *
 * For the registration-time `template=` value, this fallback is mostly a
 * belt-and-suspenders: widget.py/widget.ts's own "unknown template"
 * validation already raises at registration time, before this ever runs,
 * so it only really matters for the unbuilt `vite dev` case (no baked-in
 * opts at all) or a bundle/SDK version mismatch. But the LIVE per-ad
 * `template` value (see App's `pick()` below) has no such server-side
 * gate -- it's admin-set, external data relayed live from `/slot`, by
 * design (see the design spec) -- so for that value this fallback is the
 * ONLY thing standing between a bad/unrecognized name and a broken
 * render. Any lookup into this registry (both the live value and this
 * registration-time value) MUST go through an own-property check, not a
 * plain truthy/presence check -- see `pick()`'s comment in App() for why.
 */
const TEMPLATES: Record<
  string,
  (props: { state: SponsoredCardState; backgroundImageDataUri?: string }) => ReactNode
> = {
  card: SponsoredCard,
  banner: Banner,
  "flip-card": FlipCard,
  "scratch-reveal": ScratchReveal,
  spin: Spin,
  hero: Hero,
}
import {
  applyAccentTheme,
  fireImpressionBeacon,
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
  // Per-ad template (kin repo's LUL-64) wins when the current call's live
  // tool-result carries one AND this bundle build recognizes it. An
  // absent or unrecognized live value falls through to the
  // registration-time default instead of straight to "card" -- so a
  // typo'd/newer-than-this-build live template degrades to what the
  // integrator configured, not silently past it. `pick()` below still
  // fails open to SponsoredCard at the very end for an unrecognized (or
  // absent) registration-time value too, unchanged from before. See
  // docs/superpowers/specs/2026-09-07-per-ad-template-live-override-design.md's
  // "Precedence rule (decided)".
  //
  // Both lookups go through `Object.prototype.hasOwnProperty` rather than
  // a plain truthy `TEMPLATES[name]`/presence check: `TEMPLATES` is a
  // plain object literal, so a bracket lookup for a name like
  // "constructor", "toString", "__proto__", or "hasOwnProperty" resolves
  // through the prototype chain to a real (truthy) function -- which
  // would read as a "recognized" template even though it isn't one. The
  // registration-time value is validated server-side before this code
  // ever runs (`register_sponsored_widget()` raises on an unrecognized
  // name), but the live value is not -- it's admin-set, external data
  // relayed from `/slot` with no server-side allowlist by design (the
  // bundle's own fallback is meant to be the safety net) -- so this is
  // the first path where a prototype-chain name is reachable from live,
  // untrusted input. Left unguarded, `TEMPLATES["constructor"]` would be
  // treated as "recognized," React would throw or render nothing on the
  // resulting non-component value, and the rendered-impression beacon
  // (which fires on the loading->loaded transition, before that failure
  // is visible) would already have fired -- billing a CPM for an ad that
  // never rendered.
  const pick = (name?: string) =>
    name && Object.prototype.hasOwnProperty.call(TEMPLATES, name) ? TEMPLATES[name] : undefined
  const liveTemplate = state.kind === "loaded" ? state.template : undefined
  const Content = pick(liveTemplate) ?? pick(initialOptions?.template) ?? SponsoredCard

  // Guards the one-time loading->settled size-changed resend below so it
  // fires exactly once for that transition, never again on later
  // re-renders (e.g. this component re-rendering for unrelated reasons
  // once already settled).
  const hasSentSettledSize = useRef(false)

  // Guards the rendered-impression beacon (LUL-71) so it fires at most
  // once per widget instance, mirroring the `el.dataset.impFired` guard
  // widgets.py's fireImpressionBeacon uses for the same reason in the
  // other widget system -- belt-and-suspenders against listenForToolResult
  // somehow delivering more than one real tool-result over this widget's
  // lifetime (not expected, but a double-fired beacon would overcount a
  // publisher's own impressions, which is the wrong direction to fail in).
  const hasFiredImpression = useRef(false)

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
      // Fires the instant the disclosed content is about to become
      // visible, same as widgets.py's reference implementation -- never
      // gated on a per-template reveal interaction (FlipCard's front
      // teaser and ScratchReveal's covered content both mount as part of
      // this same "loaded" render, so "rendered" is correctly "seen" here
      // regardless of which template ends up drawn).
      if (sponsored?.impUrl && !hasFiredImpression.current) {
        hasFiredImpression.current = true
        fireImpressionBeacon(sponsored.impUrl)
      }
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
      <Content state={state} backgroundImageDataUri={initialOptions?.backgroundImageDataUri} />
      <Footer />
    </Card>
  )
}

export default App
