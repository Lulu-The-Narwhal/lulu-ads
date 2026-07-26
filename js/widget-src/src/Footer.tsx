/**
 * "Powered by Lulu Ads" disclosure footer.
 *
 * Renders once, unconditionally, as a sibling of `<SponsoredCard>` in
 * App.tsx -- never inside it, never part of the loading/loaded/noFill
 * swap (see `SponsoredCard.tsx`'s own docstring on why the footer was
 * deliberately left out of that component). This was a real gap left by
 * the plan through Task 3: no task built it. Task 4 (the final
 * self-contained-bundle assembly step) is where it's added.
 *
 * CSS matches `js/src/widget.ts`'s hand-written `.footer` rule exactly,
 * as specified by the Task 4 brief -- margin-top: 9px, padding-top: 7px,
 * a translucent-white top border, 10px text at 80% opacity, and a
 * semibold, non-underlined link that underlines on hover. That border/
 * text-color pairing was designed assuming the footer sits *inside* the
 * orange gradient `.card` (see the original CSS's `.card { color:
 * #FFF8EC }`, which the footer inherited). Here it renders outside the
 * card -- including during `loading` (skeleton, no color context) and
 * `noFill` (`SponsoredCard` renders nothing at all, so the footer is the
 * *only* visible thing) -- so it now falls back to the page's ordinary
 * text color instead of the card's cream-on-orange. That's an intentional,
 * minimal deviation to keep the footer legible against an arbitrary host
 * background in every state, not a silent change to the CSS values the
 * brief specified (those are reproduced exactly below); flagged in the
 * task report rather than guessed past silently.
 */
export function Footer() {
  return (
    <div className="mt-[9px] border-t border-white/25 pt-[7px] text-[10px] opacity-80">
      Powered by{" "}
      <a
        href="https://getlulu.dev"
        target="_blank"
        rel="noopener"
        // mcpBridge.ts's initClickRedirect() only intercepts elements
        // carrying data-url (delegated click listener, not a one-time
        // querySelectorAll("a[href]") pass like the old inline script) --
        // without this the click would be silently swallowed by the
        // sandboxed MCP Apps iframe (no allow-popups), same failure mode
        // documented on SponsoredCard's CTA button.
        data-url="https://getlulu.dev"
        className="font-semibold no-underline hover:underline"
      >
        Lulu Ads
      </a>
    </div>
  )
}
