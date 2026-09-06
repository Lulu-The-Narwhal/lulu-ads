import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import type { SponsoredCardState } from "./SponsoredCard"

/**
 * "spin" template (LUL-54): a decorative spin-and-settle flourish on the
 * logo badge. Binding guardrail from the ticket: must be deterministic --
 * a spin with multiple POSSIBLE outcomes is a gambling mechanic and is
 * explicitly not allowed. Deliberately NOT a wheel-of-fortune with
 * segments (that visual metaphor itself implies variable prizes even if
 * the code always picks one) -- this spins the single logo/badge a fixed
 * number of turns and settles, then reveals the one real offer beneath.
 * No new data need: same single text/url/cta/logo, decoration only.
 */
export function Spin({ state }: { state: SponsoredCardState }) {
  if (state.kind === "noFill") return null

  if (state.kind === "loading") {
    return (
      <div className="flex items-center gap-2.5">
        <Skeleton className="h-9 w-9 shrink-0 rounded-full bg-white/30" />
        <Skeleton className="h-3 w-full rounded-sm bg-white/30" />
      </div>
    )
  }

  const { label, text, url, logoDataUri, cta } = state

  return (
    <div className="flex items-center gap-2.5">
      <style>{`
        @keyframes lulu-spin-settle {
          0% { transform: rotate(0deg) scale(0.85); opacity: 0.6; }
          70% { transform: rotate(936deg) scale(1.08); opacity: 1; }
          100% { transform: rotate(1080deg) scale(1); opacity: 1; }
        }
        @media (prefers-reduced-motion: reduce) {
          .lulu-spin-badge { animation: none !important; }
        }
      `}</style>
      <div
        className="lulu-spin-badge flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/90"
        style={{ animation: "lulu-spin-settle 1.1s cubic-bezier(0.2, 0.8, 0.2, 1) 1" }}
      >
        {logoDataUri ? (
          <img
            src={logoDataUri}
            alt=""
            className="h-9 w-9 rounded-full object-contain p-1"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        ) : (
          <span className="text-[13px]" aria-hidden="true">
            ✦
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div
          className="text-[10px] font-extrabold tracking-[0.09em] uppercase"
          style={{ opacity: 0.92 }}
        >
          {label}
        </div>
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
  )
}
