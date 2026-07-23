# API contract

This is the wire-level contract behind every SDK method. You should rarely
need to call these endpoints directly — use the Python or TypeScript client,
or one of the framework adapters in [`integrations.md`](integrations.md) —
but if you're integrating from an unsupported language or debugging a
mismatch, this is the ground truth.

Base URL: `https://ads.getlulu.dev`

## `POST /slot`

Request a sponsored slot for the current tool call.

**Headers**

| Header | Required | Value |
|---|---|---|
| `x-api-key` | yes | your publisher `api_key` |
| `content-type` | yes | `application/json` |

**Body**

```json
{"context": {"tool": "search_flights", "category": "travel.flights"}}
```

`context` is optional and every key in it is filtered against an allowlist
before anything is sent — the SDKs do this client-side, so unlisted keys
never leave your process:

- `tool`
- `category`
- `query`
- `route`
- `locale`
- `country`

Any other key is silently dropped. Values are coerced to strings and
truncated to 200 characters. There is no field for user identity, email,
device id, or any other PII — the schema simply has nowhere to put one.

**Response — 200 (slot filled)**

```json
{"label": "Sponsored", "text": "Direct flights TLV–BKK from $412", "url": "https://ads.getlulu.dev/c/<token>"}
```

- `label` is always the literal string `"Sponsored"`.
- `url` is always a `/c/{token}` redirect link on this domain (see below),
  never a raw advertiser URL — click tracking and revenue-share attribution
  depend on going through it.

**Response — 204 (no fill)**

Empty body. This is a normal, expected outcome (no matching campaign, budget
exhausted, etc.) — not an error. Treat it exactly like a network failure:
attach nothing and move on.

**Response — 401**

Missing or invalid `x-api-key`.

**Timing**

The default SDK timeout is 800ms wall clock (covering connect + request +
parse) — 3000ms instead when the call omits an explicit `category` but
includes a `prompt`, since ads-server may run its own server-side Gemini
classification on that path (up to a 2.0s internal budget there). Neither
number is a round guess. Measured real end-to-end latency against
production `ads.getlulu.dev` with a warmed, pooled client was ~155–215ms;
measured **cold** (fresh TLS handshake + SSL context build, the common
case for real MCP tool-call traffic — sporadic human-paced calls rarely
keep a connection warm on their own) was **2.46s**. 800ms is the warm
floor plus real margin; 3000ms is sized for the classify path specifically.
Every client in this repo enforces its cap itself and returns `None`/`null`
on timeout — the contract does not depend on the server always being
fast, only on the client never waiting past the cap. Pass `timeout_ms`
(`timeoutMs` in TS) to tighten or loosen it for your own network path.

**Automatic pre-connect.** The FastMCP middleware, the LangChain
middleware, the CrewAI `install()` hook, and TypeScript's `withLuluAds`
all fire the client's `warm_up()`/`warmUp()` in the background on
construction by default (`auto_warm_up`/`autoWarmUp: false` to disable) —
this is what actually closes most of the gap between the cold (2.46s) and
warm (~200ms) numbers above for a real integrator, since it means the
very first real tool call is far more likely to land on an already-warm
connection. The base `LuluAds`/`new LuluAds` client itself does not
auto-warm — call `warm_up()`/`warmUp()` yourself at process startup if
you're using it directly without one of these adapters.

**Short-TTL cache.** Both clients also cache a successful fill result for
`cache_ttl_ms`/`cacheTtlMs` (default 45000 = 45s), keyed on the resolved
`category` when explicit, or a hash of the `prompt` text when only that's
given (so repeated identical prompts skip the classification cost too,
not just the network hop). A failure is never cached — a transient error
never suppresses a real ad for the whole TTL window. Pass
`cache_ttl_ms`/`cacheTtlMs` at construction to tune or disable it (`0`
disables caching entirely, since nothing can satisfy `expiresAt > now`
with a zero-length window).

## `GET /c/{token}`

The redirect link returned in a slot's `url` field.

- Verifies the signed `token` (opaque to clients — do not construct or parse
  it yourself).
- Records a click event, attributed back to your publisher and the campaign
  that filled the slot.
- Responds `302` to the advertiser's destination URL.
- Responds `404` if the token is invalid, tampered with, or expired.

Nothing about this endpoint requires SDK involvement — it's meant to be
followed by whatever opens the link (browser, in-app browser, etc.) after a
user clicks through from the sponsored text.

## `POST /publishers`

Registers a new publisher and issues an API key.

**Body**

```json
{"name": "my-server", "contact_email": "you@example.com", "server_url": "https://my-server.example.com"}
```

`name` and `contact_email` are required; `server_url` is optional.

**Response — 201**

```json
{"publisher_id": "pub_...", "api_key": "lk_..."}
```

The `api_key` is returned once, in this response, and is not recoverable
afterward — store it immediately (e.g. as `LULU_ADS_API_KEY`). If you lose
it, register again or contact support to rotate it.

## `POST /postback`

Reports a conversion for revenue-share accounting. This is normally called
by an affiliate network on the advertiser's behalf — not by publisher-side
code — it's documented here for completeness and for networks integrating
conversion pixels/postbacks. Lulu supplies each network with its own
postback URL (including the `key` below) when configuring the integration;
this is not a self-serve endpoint publishers or advertisers call directly.

**Auth**

Requires a `key` query-string parameter matching the shared secret Lulu
gave you when configuring your postback URL: `POST /postback?key=<secret>`.
Missing or wrong key → `401`. There is no default/open state — a postback
sent without the correct key is always rejected, never silently accepted.

**Body**

```json
{"subid": "pub_123:campaign_456:ad_789", "amount_usd": 42.00, "network": "some-network", "transaction_id": "your-own-conversion-id"}
```

- `subid` is `"{publisher_id}:{campaign_id}:{ad_id}"`, exactly as embedded
  in the click token that was followed (a legacy 2-part
  `"{publisher_id}:{campaign_id}"` form, with no `ad_id` segment, is still
  accepted for backward compatibility with clicks generated before this
  format existed).
- `amount_usd` and `network` are optional metadata.
- `transaction_id` should be your network's own unique id for this
  conversion, if you have one. Lulu uses `(network, transaction_id)` to
  detect retried/duplicate deliveries of the same postback — a duplicate
  is a no-op (`{"ok": true, "duplicate": true}`), not a double-counted
  conversion. Without a `transaction_id`, retries can't be deduplicated.

**Response — 200**

```json
{"ok": true}
```

or, on a detected retry of the same conversion:

```json
{"ok": true, "duplicate": true}
```

Publishers earn 70% of attributed CPA revenue on conversions reported this
way; payout mechanics are handled outside this API.

## Guarantees

These are the same guarantees documented in the [README](../README.md),
restated at the contract level — every SDK in this repo enforces all of
them in code, not just in prose:

- **A tool call can never break because of ads** — every failure path
  (missing creds, network error, non-200/204 response, malformed body,
  timeout) returns `None`/`null`; nothing raises.
- **Always disclosed** — `label` is hardcoded to `"Sponsored"` by the client,
  never sourced from the response body's own framing.
- **No prompt injection, ever** — the response is a plain data object
  (`label`, `text`, `url`); there is no field, anywhere in this contract,
  that instructs a model or host how to render or phrase anything.
- **No PII leaves your server** — `context` is allowlisted client-side
  before the request is even built.
- **Quality-gated** — every creative that can fill a slot has passed
  automated quality scoring (≥70) before it's eligible.
- **Intent, not identity** — matching uses the `context` you send for this
  call only; there is no persistent user profile, cookie, or cross-session
  identifier in this contract.
- **Misconfigured is still safe** — a publisher with no valid `api_key`
  never even reaches `/slot`; the client short-circuits to `None`/`null`
  with zero network calls.
