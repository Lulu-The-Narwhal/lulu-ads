import path from "node:path"
import { defineConfig } from "vitest/config"

// Separate from vite.config.ts (which pulls in @vitejs/plugin-react's babel
// transform + @tailwindcss/vite -- neither needed here, mcpBridge.ts has no
// JSX and no Tailwind classes to compile) so unit tests stay fast and don't
// depend on the app's build plugin chain.
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
  },
})
