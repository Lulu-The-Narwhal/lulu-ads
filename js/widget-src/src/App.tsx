import { useEffect, useState } from "react"
import { SponsoredCard, type SponsoredCardState } from "./SponsoredCard"
import { initClickRedirect, initHandshake, listenForToolResult } from "./mcpBridge"

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

  return <SponsoredCard state={state} />
}

export default App
