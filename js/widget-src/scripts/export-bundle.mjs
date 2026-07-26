#!/usr/bin/env node
/**
 * Runs after `vite build` (see package.json's `build` script) and turns
 * the single self-contained `dist/index.html` it produces into a checked-in
 * TypeScript source file the sibling `js/` package can import with a plain
 * `tsc` build -- `js/`'s build has no Vite/React/Tailwind step of its own
 * (see the design doc: neither published package should gain that runtime
 * toolchain as a dependency), so the compiled bundle has to cross that
 * boundary as a plain string constant, generated here and committed to
 * git like any other checked-in generated source.
 *
 * Whoever changes `widget-src/` and wants the published `lulu-ads` package
 * to pick it up must run `npm run build` here (which includes this step)
 * and commit the resulting `js/src/generatedWidgetBundle.ts` alongside
 * their source changes -- there is no build-time wiring between the two
 * packages that does this automatically.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distHtmlPath = path.resolve(__dirname, "../dist/index.html");
const outPath = path.resolve(__dirname, "../../src/generatedWidgetBundle.ts");

const html = readFileSync(distHtmlPath, "utf8");

if (!html.includes("__LULU_ADS_OPTS__")) {
  throw new Error(
    "export-bundle: dist/index.html is missing the __LULU_ADS_OPTS__ placeholder -- " +
      "sponsoredWidgetHtml() has nothing to substitute into. Check index.html still " +
      "has the #lulu-ads-opts div and that nothing upstream (e.g. HTML minification) " +
      "mangled the token."
  );
}
if ((html.match(/<script/g) ?? []).length === 0) {
  throw new Error("export-bundle: dist/index.html has no inline <script> -- did the vite build actually run?");
}
if (/<script[^>]*\ssrc=/.test(html) || /<link[^>]*\shref=/.test(html)) {
  throw new Error(
    "export-bundle: dist/index.html references an external <script src> or <link href> -- " +
      "it must be fully self-contained. Check vite-plugin-singlefile is still configured " +
      "in vite.config.ts."
  );
}

const generated = `/**
 * GENERATED FILE -- do not hand-edit.
 *
 * Produced by \`js/widget-src/scripts/export-bundle.mjs\` from
 * \`js/widget-src/dist/index.html\` (itself produced by \`vite build\` there,
 * via vite-plugin-singlefile -- one self-contained HTML file, everything
 * inlined). Regenerate with \`npm run build\` in \`js/widget-src/\` after any
 * change to that package's source, then commit this file alongside it.
 *
 * Consumed by \`js/src/widget.ts\`'s \`sponsoredWidgetHtml()\`, which
 * substitutes the `+ "`__LULU_ADS_OPTS__`" + ` placeholder token below with a
 * per-call, HTML-attribute-escaped JSON options blob before returning the
 * final HTML string.
 */
export const WIDGET_BUNDLE_HTML: string = ${JSON.stringify(html)};
`;

writeFileSync(outPath, generated, "utf8");
console.log(`export-bundle: wrote ${outPath} (${html.length} bytes of source HTML)`);
