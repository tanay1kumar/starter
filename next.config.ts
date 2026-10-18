import { config as loadEnv } from "dotenv";
import type { NextConfig } from "next";

// Secrets live in keys.env at the repo root (gitignored). Load them for server
// code (API routes). Values already set in the shell win.
loadEnv({ path: "keys.env", quiet: true });

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Keep the dev-tools bubble out of demo screenshots.
  devIndicators: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
