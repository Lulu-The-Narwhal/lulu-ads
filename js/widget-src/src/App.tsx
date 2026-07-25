import { useEffect, useRef, useState } from "react"
import { SponsoredCard, type SponsoredCardState } from "./SponsoredCard"
import { initClickRedirect, initHandshake, listenForToolResult, notifySizeChanged } from "./mcpBridge"

/**
 * The widget's React root. Starts in the skeleton state, then swaps to
 * `loaded`/`noFill` once the host's `ui/notifications/tool-result` message
 * for this call arrives -- see mcpBridge.ts for the message contract and
 * the ported handshake/click-redirect behaviors.
 *
 * Note: the "Powered by Lulu Ads" footer (design doc: renders once,
 * outside the skeleton/loaded/noFill swap, in all three states) is
 * intentionally NOT added here. Task 3's brief scopes this file to state
 * wiring + rendering `<SponsoredCard state={state} />` only, and no task
 * brief in the plan (checked Task 3 and Task 4) explicitly owns building
 * the footer shell -- flagged as a gap in the task-3 report rather than
 * guessed at here.
 */
function App() {
  const [state, setState] = useState<SponsoredCardState>({ kind: "loading" })

  // Guards the one-time loading->settled size-changed resend below so it
  // fires exactly once for that transition, never again on later
  // re-renders (e.g. this component re-rendering for unrelated reasons
  // once already settled).
  const hasSentSettledSize = useRef(false)

  useEffect(() => {
    // MCP Apps handshake -- must fire regardless of whether/when a
    // tool-result ever arrives, so the host un-hides the iframe at all.
    initHandshake()

    // CTA clicks (SponsoredCard's Button carries data-url={url}) redirect
    // through ui/open-link instead of a raw navigation, which the
    // sandboxed iframe would otherwise swallow.
    const unsubscribeClicks = initClickRedirect()

    const unsubscribeToolResult = listenForToolResult((sponsored) => {
      setState(sponsored ? { kind: "loaded", ...sponsored } : { kind: "noFill" })
    })

    return () => {
      unsubscribeClicks()
      unsubscribeToolResult()
    }
  }, [])

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

  return <SponsoredCard state={state} />
}

export default App
