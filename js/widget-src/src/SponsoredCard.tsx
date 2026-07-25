import type { CSSProperties } from "react"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

/**
 * Visual states for the sponsored card widget. Mirrors the current
 * hand-written widget (js/src/widget.ts's sponsoredWidgetHtml) which this
 * component replaces the markup of -- same brand tokens, same layout, same
 * disclosure label -- just built from shadcn/ui primitives instead of a
 * template literal.
 *
 * The footer ("Powered by Lulu Ads") is intentionally NOT part of this
 * component. It renders once in the wrapping HTML shell around
 * SponsoredCard, regardless of state, and is never itself skeletonized.
 */
export type SponsoredCardState =
  | { kind: "loading" }
  | {
      kind: "loaded"
      label: string
      text: string
      url: string
      logoDataUri?: string
      cta: string
    }
  | { kind: "noFill" }

// Lulu brand tokens -- keep in sync with js/src/widget.ts's
// ACCENT / ACCENT_LIGHT / ACCENT_DARK constants.
const ACCENT = "#E07A00"
const ACCENT_LIGHT = "#F5A623"
const ACCENT_DARK = "#B55E00"

const cardStyle: CSSProperties = {
  background: `linear-gradient(135deg, ${ACCENT_LIGHT} 0%, ${ACCENT} 55%, ${ACCENT_DARK} 100%)`,
  border: "1px solid rgba(255, 255, 255, 0.22)",
  boxShadow:
    "0 1px 2px rgba(0, 0, 0, 0.22), 0 10px 24px -10px rgba(224, 122, 0, 0.65)",
  color: "#FFF8EC",
}

export function SponsoredCard({ state }: { state: SponsoredCardState }) {
  if (state.kind === "noFill") {
    // No ad to show -- occupy no visible space. Matches today's behavior
    // when sponsored_slot() returns None: no card at all.
    return null
  }

  if (state.kind === "loading") {
    return (
      <Card
        className="gap-0 rounded-[14px] bg-muted/60 p-3.5 px-4 py-3.5 ring-0"
        aria-busy="true"
        aria-label="Loading sponsored content"
      >
        {/* label line */}
        <Skeleton className="mb-2 h-2.5 w-16 rounded-sm" />
        <div className="flex items-start gap-2.5">
          {/* logo block */}
          <Skeleton className="h-7 w-7 shrink-0 rounded-lg" />
          {/* text lines */}
          <div className="flex-1 space-y-1.5 pt-0.5">
            <Skeleton className="h-3 w-full rounded-sm" />
            <Skeleton className="h-3 w-3/5 rounded-sm" />
          </div>
        </div>
      </Card>
    )
  }

  const { label, text, url, logoDataUri, cta } = state

  return (
    <Card
      className="gap-0 rounded-[14px] border-0 p-3.5 px-4 py-3.5 ring-0"
      style={cardStyle}
    >
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
              // A raw (non-data:) logo_url can be CSP-blocked inside a real
              // host's sandboxed iframe (deferred CSP risk, see Task 1/6
              // findings) -- degrade invisibly instead of showing a broken-
              // image glyph.
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
    </Card>
  )
}
