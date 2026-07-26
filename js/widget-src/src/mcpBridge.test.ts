import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { extractSponsored, listenForToolResult, initHandshake, initClickRedirect, openLink } from "./mcpBridge"

/** Task 1's confirmed real payload shape (progress.md):
 * {jsonrpc:"2.0", method:"ui/notifications/tool-result", params:
 * {content:[...], isError:false, structuredContent:{...tool's own
 * fields..., sponsored:{label,text,url,logo_url}}}} */
function toolResultMessage(sponsored?: Record<string, unknown>) {
  return {
    jsonrpc: "2.0",
    method: "ui/notifications/tool-result",
    params: {
      content: [{ type: "text", text: "some tool output" }],
      isError: false,
      structuredContent: {
        someToolField: "unrelated tool data",
        ...(sponsored !== undefined ? { sponsored } : {}),
      },
    },
  }
}

describe("extractSponsored", () => {
  it("extracts sponsored fields from the confirmed real payload shape", () => {
    const msg = toolResultMessage({
      label: "Sponsored",
      text: "Save 15% at checkout",
      url: "https://example.com/deal",
      logo_url: "https://example.com/logo.png",
    })
    expect(extractSponsored(msg)).toEqual({
      label: "Sponsored",
      text: "Save 15% at checkout",
      url: "https://example.com/deal",
      logoDataUri: "https://example.com/logo.png",
      cta: "Learn more →",
    })
  })

  it("returns null when the sponsored field is absent (no-fill case)", () => {
    const msg = toolResultMessage(undefined)
    expect(extractSponsored(msg)).toBeNull()
  })

  it("returns null when sponsored is missing required text/url", () => {
    expect(extractSponsored(toolResultMessage({ label: "Sponsored" }))).toBeNull()
    expect(extractSponsored(toolResultMessage({ text: "x" }))).toBeNull()
  })

  it("defaults label to 'Sponsored' when absent", () => {
    const msg = toolResultMessage({ text: "hi", url: "https://x.example" })
    expect(extractSponsored(msg)?.label).toBe("Sponsored")
  })

  it("accepts camelCase logoUrl as a fallback for the cross-SDK naming inconsistency", () => {
    const msg = toolResultMessage({ text: "hi", url: "https://x.example", logoUrl: "https://x.example/l.png" })
    expect(extractSponsored(msg)?.logoDataUri).toBe("https://x.example/l.png")
  })

  it("omits logoDataUri when no logo field is present", () => {
    const msg = toolResultMessage({ text: "hi", url: "https://x.example" })
    expect(extractSponsored(msg)?.logoDataUri).toBeUndefined()
  })
})

describe("listenForToolResult", () => {
  let unsubscribe: (() => void) | undefined

  afterEach(() => {
    unsubscribe?.()
    unsubscribe = undefined
  })

  it("fires the callback with parsed data on a real tool-result message", () => {
    const onResult = vi.fn()
    unsubscribe = listenForToolResult(onResult)
    const msg = toolResultMessage({
      label: "Sponsored",
      text: "Save 15%",
      url: "https://example.com",
    })
    window.dispatchEvent(new MessageEvent("message", { data: msg }))
    expect(onResult).toHaveBeenCalledTimes(1)
    expect(onResult).toHaveBeenCalledWith({
      label: "Sponsored",
      text: "Save 15%",
      url: "https://example.com",
      logoDataUri: undefined,
      cta: "Learn more →",
    })
  })

  it("fires the callback with null when sponsored is absent", () => {
    const onResult = vi.fn()
    unsubscribe = listenForToolResult(onResult)
    window.dispatchEvent(new MessageEvent("message", { data: toolResultMessage(undefined) }))
    expect(onResult).toHaveBeenCalledTimes(1)
    expect(onResult).toHaveBeenCalledWith(null)
  })

  it("does not fire the callback for an unrelated method", () => {
    const onResult = vi.fn()
    unsubscribe = listenForToolResult(onResult)
    window.dispatchEvent(
      new MessageEvent("message", {
        data: { jsonrpc: "2.0", method: "ui/notifications/host-context-changed", params: {} },
      })
    )
    expect(onResult).not.toHaveBeenCalled()
  })

  it("does not fire the callback for non-jsonrpc postMessage noise", () => {
    const onResult = vi.fn()
    unsubscribe = listenForToolResult(onResult)
    window.dispatchEvent(new MessageEvent("message", { data: "some unrelated string" }))
    window.dispatchEvent(new MessageEvent("message", { data: { foo: "bar" } }))
    expect(onResult).not.toHaveBeenCalled()
  })

  it("unsubscribe stops further callbacks", () => {
    const onResult = vi.fn()
    const unsub = listenForToolResult(onResult)
    unsub()
    window.dispatchEvent(new MessageEvent("message", { data: toolResultMessage(undefined) }))
    expect(onResult).not.toHaveBeenCalled()
  })
})

describe("initHandshake", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("sends ui/notifications/initialized to the parent immediately when the document is already complete", () => {
    const postMessage = vi.fn()
    vi.stubGlobal("parent", { postMessage } as unknown as Window)
    Object.defineProperty(document, "readyState", { value: "complete", configurable: true })

    initHandshake()

    expect(postMessage).toHaveBeenCalledWith(
      { jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} },
      "*"
    )
    vi.unstubAllGlobals()
  })

  it("sends initialized exactly once even if both load and the 300ms fallback fire", () => {
    const postMessage = vi.fn()
    vi.stubGlobal("parent", { postMessage } as unknown as Window)
    Object.defineProperty(document, "readyState", { value: "loading", configurable: true })

    initHandshake()
    window.dispatchEvent(new Event("load"))
    vi.advanceTimersByTime(300)

    const initializedCalls = postMessage.mock.calls.filter(
      (call) => (call[0] as { method?: string }).method === "ui/notifications/initialized"
    )
    expect(initializedCalls).toHaveLength(1)
    vi.unstubAllGlobals()
  })

  it("falls back to sending initialized after 300ms if load never fires", () => {
    const postMessage = vi.fn()
    vi.stubGlobal("parent", { postMessage } as unknown as Window)
    Object.defineProperty(document, "readyState", { value: "loading", configurable: true })

    initHandshake()
    expect(postMessage).not.toHaveBeenCalled()
    vi.advanceTimersByTime(300)
    expect(postMessage).toHaveBeenCalledWith(
      { jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} },
      "*"
    )
    vi.unstubAllGlobals()
  })
})

describe("initClickRedirect / openLink", () => {
  it("openLink posts a ui/open-link request to the parent", () => {
    const postMessage = vi.fn()
    vi.stubGlobal("parent", { postMessage } as unknown as Window)
    openLink("https://example.com/deal")
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        jsonrpc: "2.0",
        method: "ui/open-link",
        params: { url: "https://example.com/deal" },
      }),
      "*"
    )
    vi.unstubAllGlobals()
  })

  it("redirects a click on an element carrying data-url instead of a plain navigation", () => {
    const postMessage = vi.fn()
    vi.stubGlobal("parent", { postMessage } as unknown as Window)

    const button = document.createElement("button")
    button.setAttribute("data-url", "https://example.com/cta")
    document.body.appendChild(button)

    const unsubscribe = initClickRedirect()
    button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }))

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ method: "ui/open-link", params: { url: "https://example.com/cta" } }),
      "*"
    )

    unsubscribe()
    document.body.removeChild(button)
    vi.unstubAllGlobals()
  })

  it("does nothing for clicks outside any data-url element", () => {
    const postMessage = vi.fn()
    vi.stubGlobal("parent", { postMessage } as unknown as Window)

    const div = document.createElement("div")
    document.body.appendChild(div)
    const unsubscribe = initClickRedirect()
    div.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }))
    expect(postMessage).not.toHaveBeenCalled()

    unsubscribe()
    document.body.removeChild(div)
    vi.unstubAllGlobals()
  })
})
