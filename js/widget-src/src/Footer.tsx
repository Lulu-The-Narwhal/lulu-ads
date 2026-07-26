/**
 * "Powered by Lulu Ads" disclosure footer.
 *
 * Renders once, unconditionally, nested inside App.tsx's single persistent
 * `<Card style={cardStyle}>` shell -- alongside `<SponsoredCard>`'s
 * swappable inner content, present in every state (loading/loaded/
 * noFill, including `noFill` where `SponsoredCard` itself renders
 * nothing and the footer is the only visible content in the card).
 *
 * CSS matches `js/src/widget.ts`'s hand-written `.footer` rule exactly --
 * margin-top: 9px, padding-top: 7px, a translucent-white top border, 10px
 * text at 80% opacity, and a semibold, non-underlined link that underlines
 * on hover. This border/text-color pairing is designed assuming the
 * footer sits *inside* the orange gradient card (see `cardStyle` in
 * SponsoredCard.tsx, which sets `color: #FFF8EC` on the card), and now
 * that it's actually nested inside that card in App.tsx, it inherits that
 * cream text color via normal CSS inheritance, matching the original
 * hand-written widget's layout.
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
