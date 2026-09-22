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
          nothing rather than a placeholder.

          Why the card is written here rather than pulled from the SDK:
          `sponsoredWidgetHtml()` (lulu-ads/widget) returns a COMPLETE HTML
          document -- 276KB, of which 243KB is the MCP Apps runtime bridge and
          only ~1.9KB is markup. It is meant to BE an MCP Apps resource, served
          whole into an iframe. A Skybridge view already is that resource and
          already has that runtime, so embedding it would ship the machinery
          twice. Inside a view, render the data. */}
      {sponsored && (
        <a
          href={sponsored.url}
          target="_blank"
          rel="noopener noreferrer sponsored"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginTop: 18,
            padding: "12px 14px",
            border: "1px solid rgba(127,127,127,0.22)",
            borderLeft: "3px solid #E07A00",
            borderRadius: 10,
            textDecoration: "none",
            color: "inherit",
            background: "rgba(127,127,127,0.04)",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <span
              style={{
                display: "block",
                fontSize: 10,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: 0.6,
                opacity: 0.55,
              }}
            >
              {/* From the payload. Do not hardcode or reword it: the label is
                  the disclosure, and the SDK sets it, not the advertiser. */}
              {sponsored.label}
            </span>
            <div style={{ marginTop: 3, lineHeight: 1.35 }}>{sponsored.text}</div>
          </div>
          <span aria-hidden="true" style={{ opacity: 0.4, fontSize: 18 }}>
            &rsaquo;
          </span>
        </a>
      )}
    </div>
  );
}

mountView(<FlightResults />);
