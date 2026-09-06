import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import App from "./App"

// react-dom's act() checks this global before allowing batched updates in
// a non-browser test environment; without it every act() call warns.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

/**
 * Covers Fix 2 from the Task 3 review: initHandshake() only measures/sends
 * size-changed for the initial skeleton. Nothing re-sent it when the real
 * tool-result later swaps state.kind away from "loading" (to "loaded" or
 * "noFill"), which has a different height -- so a real host kept the
 * skeleton's height reserved after the swap. These tests assert the
 * one-time resend added in App.tsx actually fires on that transition, and
 * only once, not on every re-render.
 */

function toolResultMessage(sponsored?: Record<string, unknown>) {
  return {
    jsonrpc: "2.0",
    method: "ui/notifications/tool-result",
    params: {
      content: [{ type: "text", text: "some tool output" }],
      isError: false,
      structuredContent: {
        ...(sponsored !== undefined ? { sponsored } : {}),
      },
    },
  }
}

function sizeChangedCalls(postMessage: ReturnType<typeof vi.fn>) {
  return postMessage.mock.calls.filter(
    (call) => (call[0] as { method?: string }).method === "ui/notifications/size-changed"
  )
}

describe("App: loading->settled size-changed resend", () => {
  let container: HTMLDivElement
  let root: Root
  let postMessage: ReturnType<typeof vi.fn>

  beforeEach(() => {
    container = document.createElement("div")
    document.body.appendChild(container)

    postMessage = vi.fn()
    vi.stubGlobal("parent", { postMessage } as unknown as Window)

    // jsdom doesn't lay out real content, so document.body.scrollHeight is
    // always 0 by default -- notifySizeChanged() no-ops on a falsy height.
    // Stub a non-zero height so the resend under test is actually exercised.
    Object.defineProperty(document.body, "scrollHeight", {
      value: 240,
      configurable: true,
    })

    Object.defineProperty(document, "readyState", { value: "complete", configurable: true })
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    vi.unstubAllGlobals()
  })

  it("sends exactly one extra size-changed on the loading->loaded transition", async () => {
    await act(async () => {
      root = createRoot(container)
      root.render(<App />)
    })

    // Initial handshake already sent one size-changed for the skeleton.
    const afterMount = sizeChangedCalls(postMessage).length
    expect(afterMount).toBe(1)

    await act(async () => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: toolResultMessage({ text: "Save 15%", url: "https://example.com" }),
        })
      )
    })

    expect(sizeChangedCalls(postMessage)).toHaveLength(2)
  })

  it("sends exactly one extra size-changed on the loading->noFill transition", async () => {
    await act(async () => {
      root = createRoot(container)
      root.render(<App />)
    })
    expect(sizeChangedCalls(postMessage)).toHaveLength(1)

    await act(async () => {
      window.dispatchEvent(new MessageEvent("message", { data: toolResultMessage(undefined) }))
    })

    expect(sizeChangedCalls(postMessage)).toHaveLength(2)
  })

  it("does not resend size-changed again on subsequent re-renders once settled", async () => {
    await act(async () => {
      root = createRoot(container)
      root.render(<App />)
    })

    await act(async () => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: toolResultMessage({ text: "Save 15%", url: "https://example.com" }),
        })
      )
    })
    expect(sizeChangedCalls(postMessage)).toHaveLength(2)

    // Force additional re-renders after settling (App re-rendering for
    // unrelated reasons, e.g. parent-driven prop churn simulated here via
    // re-rendering the same element).
    await act(async () => {
      root.render(<App />)
    })
    await act(async () => {
      root.render(<App />)
    })

    expect(sizeChangedCalls(postMessage)).toHaveLength(2)
  })
})

/**
 * Template dispatch (LUL-46 registry / LUL-47 banner): App.tsx picks the
 * inner content component from `initialOptions.template`, defaulting to
 * "card" (SponsoredCard) when absent/unrecognized. Structural discriminator
 * used below: SponsoredCard's loaded state has no `<span>` anywhere (label
 * is a `<div>`, everything else is `<div>`/`<img>`/a shadcn Button) --
 * Banner's loaded state renders its label as a `<span>`. Real content
 * (label/text/cta) is identical between templates by design, so a text-only
 * assertion couldn't tell them apart; this checks which component actually
 * mounted.
 */
describe("App: template dispatch", () => {
  let container: HTMLDivElement
  let root: Root
  let optsEl: HTMLElement

  function setOpts(opts: Record<string, unknown> | null) {
    optsEl.setAttribute("data-opts", opts ? JSON.stringify(opts) : "")
  }

  beforeEach(() => {
    container = document.createElement("div")
    document.body.appendChild(container)
    optsEl = document.createElement("div")
    optsEl.id = "lulu-ads-opts"
    document.body.appendChild(optsEl)
    vi.stubGlobal("parent", { postMessage: vi.fn() } as unknown as Window)
    Object.defineProperty(document, "readyState", { value: "complete", configurable: true })
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
    optsEl.remove()
    vi.unstubAllGlobals()
  })

  async function renderWithToolResult(sponsored: Record<string, unknown>) {
    await act(async () => {
      root = createRoot(container)
      root.render(<App />)
    })
    await act(async () => {
      window.dispatchEvent(new MessageEvent("message", { data: toolResultMessage(sponsored) }))
    })
  }

  it("renders SponsoredCard (no span) when template is card", async () => {
    setOpts({ text: "x", url: "https://x.com", template: "card" })
    await renderWithToolResult({ text: "Save 15%", url: "https://example.com" })
    expect(container.querySelector("span")).toBeNull()
  })

  it("renders Banner (label as span) when template is banner", async () => {
    setOpts({ text: "x", url: "https://x.com", template: "banner" })
    await renderWithToolResult({ text: "Save 15%", url: "https://example.com" })
    expect(container.querySelector("span")?.textContent).toBe("Sponsored")
  })

  it("falls back to card for an unrecognized template value", async () => {
    setOpts({ text: "x", url: "https://x.com", template: "does-not-exist" })
    await renderWithToolResult({ text: "Save 15%", url: "https://example.com" })
    expect(container.querySelector("span")).toBeNull()
  })

  it("falls back to card when initialOptions is absent entirely", async () => {
    setOpts(null)
    await renderWithToolResult({ text: "Save 15%", url: "https://example.com" })
    expect(container.querySelector("span")).toBeNull()
  })
})
