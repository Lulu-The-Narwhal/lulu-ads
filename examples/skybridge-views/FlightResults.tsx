/**
 * Skybridge view for skybridge_server.ts's `search_flights`.
 *
 * In a real Skybridge app this file lives in your `src/views/` directory and
 * is built by Skybridge's Vite plugin -- it is included here as the reference
 * for HOW to render the sponsored card, not as a standalone runnable.
 * `view: { component: "FlightResults" }` on the tool is what binds them.
 *
 * The point: because `search_flights` declares no outputSchema, the SDK puts
 * `sponsored` directly into structuredContent, which is what this view reads.
 * A tool WITH an outputSchema only gets it on _meta (adding an unlisted field
 * would fail the client's validation) -- the fallback below covers that case
 * so one view handles both.
 *
 * Disclosure: `sponsored` is data. The SDK never tells a model or a view to
 * display it -- rendering it is this file's decision, and if you render it you
 * label it. The label ships in the payload; use it rather than inventing copy.
 */
import { mountView } from "skybridge/web";
import { useToolInfo } from "../helpers";

type Flight = { carrier: string; priceUsd: number; stops: number };
type Sponsored = { label: string; text: string; url: string };

function FlightResults() {
  const toolInfo = useToolInfo<"search_flights">();
  const out = (toolInfo?.output ?? {}) as {
    origin?: string;
    destination?: string;
    flights?: Flight[];
    sponsored?: Sponsored;
  };

  // Schemaless tools get it in structuredContent; schema'd tools only on _meta.
  const sponsored: Sponsored | undefined =
    out.sponsored ?? (toolInfo?._meta?.["ads.getlulu.dev/sponsored"] as Sponsored | undefined);

  const flights = out.flights ?? [];

  return (
    <div style={{ font: "14px system-ui", padding: 16 }}>
      <h2 style={{ margin: "0 0 12px", fontSize: 16 }}>
        {out.origin} → {out.destination}
      </h2>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
            <th style={{ padding: "6px 4px" }}>Carrier</th>
            <th style={{ padding: "6px 4px" }}>Stops</th>
            <th style={{ padding: "6px 4px", textAlign: "right" }}>Price</th>
          </tr>
        </thead>
        <tbody>
          {flights.map((f) => (
            <tr key={f.carrier} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td style={{ padding: "6px 4px" }}>{f.carrier}</td>
              <td style={{ padding: "6px 4px" }}>{f.stops === 0 ? "Non-stop" : `${f.stops} stop`}</td>
              <td style={{ padding: "6px 4px", textAlign: "right" }}>${f.priceUsd}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Absent on a no-fill. That is normal and never an error -- render
          nothing rather than a placeholder. */}
      {sponsored && (
        <a
          href={sponsored.url}
          target="_blank"
          rel="noopener noreferrer sponsored"
          style={{
            display: "block",
            marginTop: 14,
            padding: "10px 12px",
            border: "1px solid #e2e2e2",
            borderRadius: 8,
            textDecoration: "none",
            color: "inherit",
          }}
        >
          <span
            style={{
              fontSize: 11,
              textTransform: "uppercase",
              letterSpacing: 0.4,
              opacity: 0.6,
            }}
          >
            {/* Comes from the payload -- do not hardcode or reword it. */}
            {sponsored.label}
          </span>
          <div style={{ marginTop: 2 }}>{sponsored.text}</div>
        </a>
      )}
    </div>
  );
}

mountView(<FlightResults />);
