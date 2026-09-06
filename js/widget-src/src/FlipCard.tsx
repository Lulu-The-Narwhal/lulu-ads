import { useState } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import type { SponsoredCardState } from "./SponsoredCard"

/**
 * "flip-card" template (LUL-53): a pure-CSS 3D flip on tap. Front face is
 * the disclosed label + logo (a teaser, not a puzzle -- the label always
 * says "Sponsored" up front, nothing is hidden about WHAT this is, only
 * the offer's own text/CTA are revealed on flip). Back face carries the
 * real text + CTA. No new data need: this only needs the ONE offer's
 * existing text/url/cta, split across two faces rather than into a
 * separate front/back content field -- see LUL-53's own note that the
 * split is presentational, not a new data requirement.
 *
 * Keyboard/no-JS-interaction accessible via a real <button> toggling
 * state, not a hover-only CSS trick -- works identically on touch (tap)
 * and desktop (click).
 */
export function FlipCard({ state }: { state: SponsoredCardState }) {
  const [flipped, setFlipped] = useState(false)

  if (state.kind === "noFill") return null

  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2.5">
        <Skeleton className="h-9 w-9 shrink-0 rounded-lg bg-white/30" />
        <div className="flex-1 space-y-1.5">
          <Skeleton className="h-2.5 w-16 rounded-sm bg-white/30" />
          <Skeleton className="h-3 w-3/4 rounded-sm bg-white/30" />
        </div>
      </div>
    )
  }

  const { label, text, url, logoDataUri, cta } = state

  return (
    <div style={{ perspective: "800px" }}>
      <button
        type="button"
        onClick={() => setFlipped((f) => !f)}
        aria-label={flipped ? "Show sponsor" : `${label}: tap to reveal offer`}
        className="w-full cursor-pointer border-0 bg-transparent p-0 text-left"
        style={{
          position: "relative",
          minHeight: "44px",
          transformStyle: "preserve-3d",
          transition: "transform 0.5s",
          transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)",
        }}
      >
        {/* Front: the disclosed label + logo -- always visible first,
            never hides WHAT this is, only the offer details. */}
        <div
          className="flex items-center gap-2.5"
          style={{ backfaceVisibility: "hidden" }}
        >
          {logoDataUri ? (
            <img
              src={logoDataUri}
              alt=""
              className="h-9 w-9 shrink-0 rounded-lg bg-white/90 object-contain p-1"
              onError={(e) => {
                e.currentTarget.style.display = "none"
              }}
            />
          ) : null}
          <div>
            <div
              className="text-[10px] font-extrabold tracking-[0.09em] uppercase"
              style={{ opacity: 0.92 }}
            >
              {label}
            </div>
            <div className="text-[12px] opacity-80">Tap to reveal offer</div>
          </div>
        </div>

        {/* Back: the real offer + CTA. Positioned to overlay the front
            face and pre-flipped 180deg so it reads right-side-up once the
            outer element finishes its own rotation. */}
        <div
          className="text-[13px] leading-[1.45]"
          style={{
            position: "absolute",
            inset: 0,
            backfaceVisibility: "hidden",
            transform: "rotateY(180deg)",
          }}
        >
          {text}{" "}
          <Button
            variant="link"
            data-url={url}
            className="h-auto p-0 align-baseline text-[13px] font-bold text-white underline decoration-white underline-offset-2 hover:text-white"
          >
            {cta}
          </Button>
        </div>
      </button>
    </div>
  )
}
