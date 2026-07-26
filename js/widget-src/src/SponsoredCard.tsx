import type { CSSProperties } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

/**
 * Visual states for the sponsored card widget. Mirrors the current
 * hand-written widget (js/src/widget.ts's sponsoredWidgetHtml) which this
 * component replaces the markup of -- same brand tokens, same layout, same
 * disclosure label -- just built from shadcn/ui primitives instead of a
 * template literal.
 *
 * This component renders only the INNER content for each state -- the
 * label/skeleton/logo/text row, never an outer `<Card>`. App.tsx owns a
 * single persistent `<Card style={cardStyle}>` that wraps this component's
 * output together with `<Footer />` in every state (loading/loaded/
 * noFill), so the orange gradient card shell and the footer's divider
 * never flicker in or out of existence -- only the inner content swaps.
 * `cardStyle` is exported below for App.tsx to use on that persistent
 * wrapper.
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
// ACCENT / ACCENT_LIGHT / ACCENT_DARK constants. Read through CSS custom
// properties (with these hex values as the `var()` fallback) rather than
// hardcoded directly, so `mcpBridge.ts`'s `applyAccentTheme` -- called
// once at startup from per-integrator `sponsoredWidgetHtml({accent,
// accentLight, accentDark})` options -- can actually override them. Before
// this, a custom `accent` option silently did nothing: this component
// only ever rendered these hardcoded constants.
const ACCENT = "#E07A00"
const ACCENT_LIGHT = "#F5A623"
const ACCENT_DARK = "#B55E00"

export const cardStyle: CSSProperties = {
  background: `linear-gradient(135deg, var(--lulu-accent-light, ${ACCENT_LIGHT}) 0%, var(--lulu-accent, ${ACCENT}) 55%, var(--lulu-accent-dark, ${ACCENT_DARK}) 100%)`,
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
      <>
        {/* label line */}
        <Skeleton className="mb-2 h-2.5 w-16 rounded-sm bg-white/30" />
        <div className="flex items-start gap-2.5">
          {/* logo block */}
          <Skeleton className="h-7 w-7 shrink-0 rounded-lg bg-white/30" />
          {/* text lines */}
          <div className="flex-1 space-y-1.5 pt-0.5">
            <Skeleton className="h-3 w-full rounded-sm bg-white/30" />
            <Skeleton className="h-3 w-3/5 rounded-sm bg-white/30" />
          </div>
        </div>
      </>
    )
  }

  const { label, text, url, logoDataUri, cta } = state

  return (
    <>
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
    </>
  )
}
