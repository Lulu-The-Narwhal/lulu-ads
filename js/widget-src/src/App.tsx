import { SponsoredCard, type SponsoredCardState } from "./SponsoredCard"

// Visual QA harness for Task 2 -- not the final widget shell (that's
// Task 3+). Renders all three states side by side at the widget's real
// width so skeleton/loaded/no-fill can be eyeballed in one screenshot.
const loadedState: SponsoredCardState = {
  kind: "loaded",
  label: "Sponsored",
  text: "Save 15% at checkout with our partner",
  url: "https://example.com/deal",
  cta: "Learn more →",
}

const loadedWithLogoState: SponsoredCardState = {
  ...loadedState,
  logoDataUri:
    "data:image/svg+xml;base64," +
    btoa(
      '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28"><rect width="28" height="28" rx="6" fill="#E07A00"/><text x="14" y="19" font-size="14" text-anchor="middle" fill="white">L</text></svg>'
    ),
}

function Demo({ title, state }: { title: string; state: SponsoredCardState }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <p style={{ font: "12px monospace", color: "#666", marginBottom: 6 }}>
        {title}
      </p>
      <div style={{ width: 360 }}>
        <SponsoredCard state={state} />
      </div>
    </div>
  )
}

function App() {
  return (
    <div style={{ padding: 24, fontFamily: "-apple-system, sans-serif" }}>
      <Demo title="loading" state={{ kind: "loading" }} />
      <Demo title="loaded (no logo)" state={loadedState} />
      <Demo title="loaded (with logo)" state={loadedWithLogoState} />
      <Demo title="noFill (renders nothing below)" state={{ kind: "noFill" }} />
    </div>
  )
}

export default App
