import type { NextConfig } from "next";
import { proxyRewrites } from "./proxy.config";

const nextConfig: NextConfig = {
  async rewrites() {
    return proxyRewrites({
      API_ORIGIN: process.env.API_ORIGIN,
      AI_ORIGIN: process.env.AI_ORIGIN,
    });
  },
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
  turbopack: {
    rules: {
      "globals.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
