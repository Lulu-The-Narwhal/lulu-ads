import { useEffect, useRef, useState } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import type { SponsoredCardState } from "./SponsoredCard"

const AUTO_REVEAL_MS = 3000
const CLEAR_THRESHOLD = 0.55

/**
 * "scratch-reveal" template (LUL-52): the offer sits underneath an opaque
 * canvas layer the viewer scratches away (pointer drag, `destination-out`
 * compositing). Auto-reveals after AUTO_REVEAL_MS regardless of
 * interaction -- binding guardrail from the ticket: the underlying offer
 * is identical whether or not anyone scratches, this is a reveal
 * animation, never gated content. No new data need -- same single
 * text/url/cta/logo underneath, just a different reveal mechanic on top.
 */
export function ScratchReveal({ state }: { state: SponsoredCardState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [revealed, setRevealed] = useState(false)
  const scratchingRef = useRef(false)
  const clearedPixelsRef = useRef(0)

  useEffect(() => {
    if (state.kind !== "loaded" || revealed) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width
    canvas.height = rect.height

    ctx.globalCompositeOperation = "source-over"
    ctx.fillStyle = "rgba(255,255,255,0.92)"
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = "rgba(60,40,10,0.7)"
    ctx.font = "600 11px system-ui, sans-serif"
    ctx.textAlign = "center"
    ctx.fillText("Scratch to reveal", canvas.width / 2, canvas.height / 2 + 4)

    const totalPixels = canvas.width * canvas.height

    function scratchAt(x: number, y: number) {
      if (!ctx) return
      ctx.globalCompositeOperation = "destination-out"
      ctx.beginPath()
      ctx.arc(x, y, 16, 0, Math.PI * 2)
      ctx.fill()
      clearedPixelsRef.current += Math.PI * 16 * 16
      if (clearedPixelsRef.current / totalPixels > CLEAR_THRESHOLD) {
        setRevealed(true)
      }
    }

    function posFromEvent(e: PointerEvent) {
      const r = canvas!.getBoundingClientRect()
      return { x: e.clientX - r.left, y: e.clientY - r.top }
    }

    function onDown(e: PointerEvent) {
      scratchingRef.current = true
      const { x, y } = posFromEvent(e)
      scratchAt(x, y)
    }
    function onMove(e: PointerEvent) {
      if (!scratchingRef.current) return
      const { x, y } = posFromEvent(e)
      scratchAt(x, y)
    }
    function onUp() {
      scratchingRef.current = false
    }

    canvas.addEventListener("pointerdown", onDown)
    canvas.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)

    // Binding guardrail: reveal is guaranteed regardless of interaction --
    // this is a reveal ANIMATION, never gated content.
    const timer = setTimeout(() => setRevealed(true), AUTO_REVEAL_MS)

    return () => {
      canvas.removeEventListener("pointerdown", onDown)
      canvas.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
      clearTimeout(timer)
    }
  }, [state.kind, revealed])

  if (state.kind === "noFill") return null

  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2.5">
        <Skeleton className="h-7 w-7 shrink-0 rounded-lg bg-white/30" />
        <Skeleton className="h-3 w-full rounded-sm bg-white/30" />
      </div>
    )
  }

  const { label, text, url, logoDataUri, cta } = state

  return (
    <div style={{ position: "relative", minHeight: "44px" }}>
      <div
        className="mb-[5px] text-[10px] font-extrabold tracking-[0.09em] uppercase"
        style={{ opacity: 0.92 }}
      >
        {label}
      </div>
      <div className="flex items-start gap-2.5">
        {logoDataUri ? (
          <img
            src={logoDataUri}
            alt=""
            className="h-7 w-7 shrink-0 rounded-lg bg-white/90 object-contain p-0.5"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        ) : null}
        <div className="text-[13px] leading-[1.45]">
          {text}{" "}
          <Button
            variant="link"
            data-url={url}
            className="h-auto p-0 align-baseline text-[13px] font-bold text-white underline decoration-white underline-offset-2 hover:text-white"
          >
            {cta}
          </Button>
        </div>
      </div>
      {!revealed && (
        <canvas
          ref={canvasRef}
          data-testid="scratch-canvas"
          className="cursor-pointer rounded-md"
          style={{ position: "absolute", inset: 0, touchAction: "none" }}
        />
      )}
    </div>
  )
}
