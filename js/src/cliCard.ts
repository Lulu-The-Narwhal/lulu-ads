/**
 * Client-adaptive plain-text formatting for CLI hosts. See the Python
 * package's cli_card.py docstring for the full rationale: terminals have
 * no widget surface, so this formats the disclosed line as a bordered
 * plain-text block instead of a plain sentence — still just content[].text,
 * still zero instruction to the model about what to say.
 */
import type { Sponsored } from "./index.js";

export const KNOWN_CLI_CLIENTS: ReadonlySet<string> = new Set([
  "claude-code", // confirmed live: clientInfo.name === "claude-code" (v2.1.212)
]);

const CARD_WIDTH = 46;

function wrap(text: string, width: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = (current + " " + word).trim();
    if (candidate.length > width) {
      if (current) lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines.length ? lines : [""];
}

export function isCliClient(clientName: string | undefined | null): boolean {
  return !!clientName && KNOWN_CLI_CLIENTS.has(clientName);
}

export function formatCliCard(sponsored: Sponsored, width: number = CARD_WIDTH): string {
  const label = sponsored.label ?? "Sponsored";
  const url = sponsored.url ?? "";
  // The tracking URL (a JWT-signed https://ads.getlulu.dev/c/<token> link)
  // can run past 200 characters — forcing it inside the box blows the
  // border out to match. It stays fully intact and clickable, just printed
  // on its own line below the box instead.
  const bodyLines = wrap(sponsored.text ?? "", width);
  const innerWidth = Math.max(label.length + 2, ...bodyLines.map((l) => l.length), width);

  const top = "┌─ " + label + " " + "─".repeat(innerWidth - label.length - 1) + "┐";
  const bottom = "└" + "─".repeat(innerWidth + 2) + "┘";
  const body = bodyLines.map((line) => `│ ${line.padEnd(innerWidth)} │`).join("\n");

  const lines = [top, body, bottom];
  if (url) lines.push(`→ ${url}`);
  return lines.join("\n");
}
