import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import type { SponsoredCardState } from "./SponsoredCard"

/**
 * "hero" template (LUL-48): full-bleed background image, poster-style,
 * with the logo + text/CTA anchored near the bottom over a dark gradient
 * scrim for legibility. Falls back to the shared accent-token gradient
 * (same as every other template) when no background image was supplied --
 * "image or gradient" from the ticket's own spec.
 *
 * Bleeds past App.tsx's shared Card padding (14px vertical / 16px
 * horizontal, see App.tsx's `className`) via matching negative margins,
 * then re-applies that same padding to its own inner content so the text
 * still lines up with `<Footer/>` below it -- the only template that
 * needs this, since it's the only one whose whole point is filling the
 * card edge-to-edge rather than sitting inside the existing padding.
 *
 * Registration-time only: `backgroundImageDataUri` comes from
 * `register_sponsored_widget`'s optional `background_image` param (an
 * integrator-supplied URL, fetched once and inlined exactly like `logo`
 * already is) -- not from ads-server's automatic per-campaign matching,
 * which doesn't have an image field yet (tracked separately, LUL-63).
 * Passed as a separate prop, not part of `state`, because it's a static
 * per-widget-instance value applied once (same category as `accent` --
 * see App.tsx's `applyAccentTheme`), never something that varies per live
 * tool-result the way `logoDataUri` does.
 */
export function Hero({
  state,
  backgroundImageDataUri,
}: {
  state: SponsoredCardState
  backgroundImageDataUri?: string
}) {
  if (state.kind === "noFill") return null

  const bleedStyle = {
    margin: "-14px -16px",
    borderRadius: "14px",
    overflow: "hidden",
    position: "relative" as const,
    minHeight: "84px",
  }
  const innerStyle = { padding: "14px 16px 12px" }

  if (state.kind === "loading") {
    return (
      <div style={bleedStyle}>
        <div className="absolute inset-0 bg-black/20" />
        <div style={{ ...innerStyle, position: "relative" }} className="flex flex-col justify-end" >
          <Skeleton className="mb-1.5 h-2.5 w-16 rounded-sm bg-white/40" />
          <Skeleton className="h-3 w-3/4 rounded-sm bg-white/40" />
        </div>
      </div>
    )
  }

  const { label, text, url, logoDataUri, cta } = state

  return (
    <div style={bleedStyle}>
      {backgroundImageDataUri ? (
        <img
          src={backgroundImageDataUri}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
          onError={(e) => {
            // Fetch/CSP failure at registration time already means this
            // prop is simply absent -- this only guards a data: URI that
            // somehow fails to decode client-side. Either way, degrade to
            // the shared accent gradient underneath, never a broken-image
            // glyph filling the whole card.
            e.currentTarget.style.display = "none"
          }}
        />
      ) : null}
      {/* Scrim: guarantees the label/text/CTA stay legible over ANY
          photo, not just ones an advertiser happened to pick with
          bottom-heavy contrast. */}
      <div
        className="absolute inset-0"
        style={{ background: "linear-gradient(to top, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.05) 55%, transparent 100%)" }}
      />
      <div style={{ ...innerStyle, position: "relative" }} className="flex flex-col justify-end gap-1">
        <div
          className="text-[10px] font-extrabold tracking-[0.09em] uppercase"
          style={{ opacity: 0.95 }}
        >
          {label}
        </div>
        <div className="flex items-center gap-2">
          {logoDataUri ? (
            <img
              src={logoDataUri}
              alt=""
              className="h-6 w-6 shrink-0 rounded-md bg-white/90 object-contain p-0.5"
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
      </div>
    </div>
  )
}
