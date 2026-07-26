import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

// https://vite.dev/config/
//
// This build's only consumer is `sponsoredWidgetHtml()` (js/src/widget.ts),
// which embeds the compiled `dist/index.html` verbatim into an MCP Apps
// iframe's srcdoc/resource content. It must never reference an external
// file at runtime -- viteSingleFile() inlines the JS bundle and CSS
// straight into the HTML (no /assets/*.js, no /assets/*.css), matching the
// hand-written widget's existing "everything self-contained" discipline
// (see widget.ts's module docstring on why even the logo is inlined as a
// data: URI rather than linked).
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    // A single HTML file with everything inlined has no meaningful chunk
    // boundaries left to split -- keep the whole thing as one asset so
    // viteSingleFile has nothing left dangling outside index.html.
    cssCodeSplit: false,
    assetsInlineLimit: 100_000_000,
  },
})
