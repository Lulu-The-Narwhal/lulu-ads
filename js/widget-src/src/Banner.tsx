import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import type { SponsoredCardState } from "./SponsoredCard"

/**
 * "banner" template (LUL-47): a full-width horizontal strip -- everything
 * in one row instead of SponsoredCard's stacked label-line + logo/text
 * rows. Good fit for wide-but-short layouts (VS Code sidebar, wide CLI
 * panes) where a tall stacked card wastes width.
 *
 * Reuses the exact same shared contract as every other template: renders
 * only the INNER content for a given state -- App.tsx still owns the
 * single persistent `<Card style={cardStyle}>` + `<Footer/>` wrapping
 * this, so the disclosed label styling, gradient shell, and "Powered by
 * Lulu Ads" footer are identical to every other template, not something
 * this component has to reimplement. No background-image support yet --
 * that needs a real advertiser-supplied image field that doesn't exist on
 * `ads` today (same class of gap as LUL-63's testimonial/countdown/quiz/
 * video fields) -- "or gradient" from LUL-47's own spec is satisfied by
 * the shell's existing accent-token gradient, already applied regardless
 * of template.
 */
export function Banner({ state }: { state: SponsoredCardState }) {
  if (state.kind === "noFill") return null

  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2.5">
        <Skeleton className="h-2.5 w-12 shrink-0 rounded-sm bg-white/30" />
        <Skeleton className="h-7 w-7 shrink-0 rounded-lg bg-white/30" />
        <Skeleton className="h-3 w-full rounded-sm bg-white/30" />
      </div>
    )
  }

  const { label, text, url, logoDataUri, cta } = state

  return (
    <div className="flex items-center gap-2.5">
      <span
        className="shrink-0 text-[10px] font-extrabold tracking-[0.09em] uppercase"
        style={{ opacity: 0.92 }}
      >
        {label}
      </span>
      {logoDataUri ? (
        <img
          src={logoDataUri}
          alt=""
          className="h-7 w-7 shrink-0 rounded-lg bg-white/90 object-contain p-0.5"
          onError={(e) => {
            // Same CSP-block degrade as SponsoredCard's logo -- see its
            // onError comment for why this must fail invisibly.
            e.currentTarget.style.display = "none"
          }}
        />
      ) : null}
      <div className="min-w-0 flex-1 truncate text-[13px] leading-[1.45]">
        {text}{" "}
        <Button
          variant="link"
          data-url={url}
          className="h-auto p-0 align-baseline text-[13px] font-bold whitespace-nowrap text-white underline decoration-white underline-offset-2 hover:text-white"
        >
          {cta}
        </Button>
      </div>
    </div>
  )
}
