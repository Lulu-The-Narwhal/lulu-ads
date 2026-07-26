import { defineConfig } from "vitest/config";

// Without an explicit include/exclude, vitest's default file discovery is
// recursive and picks up `widget-src/src/**/*.test.ts(x)` too -- that
// package is a fully independent tool (its own package.json, its own
// jsdom-based vitest.config.ts, its own React/Vite toolchain, deliberately
// not a dependency of the published `lulu-ads` package per the design
// doc) and running its tests under *this* package's plain-node vitest
// environment fails immediately (`window`/`document` undefined -- no
// jsdom here). Scope this package's test run to its own `test/` directory
// and run widget-src's suite the normal way, from inside widget-src/.
export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
  },
});
