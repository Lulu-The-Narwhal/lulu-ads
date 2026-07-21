import { expect, test } from "vitest";
import { formatCliCard, isCliClient } from "../src/cliCard.js";

test("isCliClient matches known names only", () => {
  expect(isCliClient("claude-code")).toBe(true);
  expect(isCliClient("claude-ai")).toBe(false);
  expect(isCliClient(undefined)).toBe(false);
  expect(isCliClient(null)).toBe(false);
});

test("formatCliCard has rounded border and footer", () => {
  const card = formatCliCard({ label: "Sponsored", text: "Save 15% at checkout", url: "https://x.co/1" });
  const lines = card.split("\n");
  expect(lines[0].startsWith("╭─ Sponsored")).toBe(true);
  expect(lines[0].endsWith("╮")).toBe(true);
  expect(lines[lines.length - 2].startsWith("╰─ via Lulu Ads")).toBe(true);
  expect(lines[lines.length - 2].endsWith("╯")).toBe(true);
  expect(lines[lines.length - 1]).toBe("→ https://x.co/1");
  const widths = new Set(lines.slice(0, -1).map((l) => l.length));
  expect(widths.size).toBe(1);
});

test("formatCliCard keeps long urls outside the box", () => {
  const longUrl = "https://ads.getlulu.dev/c/" + "a".repeat(200);
  const card = formatCliCard({ label: "Sponsored", text: "short", url: longUrl });
  const lines = card.split("\n");
  expect(lines[lines.length - 1]).toBe(`→ ${longUrl}`);
  expect(Math.max(...lines.slice(0, -1).map((l) => l.length))).toBeLessThan(80);
});

test("formatCliCard omits link line when url is empty", () => {
  const card = formatCliCard({ label: "Sponsored", text: "hi", url: "" });
  expect(card.includes("→")).toBe(false);
});
