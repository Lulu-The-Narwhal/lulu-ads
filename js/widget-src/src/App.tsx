import { useEffect, useRef, useState } from "react"
import { SponsoredCard, type SponsoredCardState } from "./SponsoredCard"
import { Footer } from "./Footer"
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
 * Renders `<Footer />` unconditionally, as a sibling of `<SponsoredCard>`
 * -- outside the loading/loaded/noFill swap, present in every state
 * (including `noFill`, where `SponsoredCard` itself renders nothing). See
 * Footer.tsx for why: this was a real gap no task before Task 4 built.
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
    <>
      <SponsoredCard state={state} />
      <Footer />
    </>
  )
}

export default App
