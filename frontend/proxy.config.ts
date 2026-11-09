function origin(value: string) {
  const parsed = new URL(value);
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username || parsed.password || parsed.search || parsed.hash ||
    parsed.pathname !== "/"
  ) throw new Error("Proxy upstream must be an HTTP(S) origin without credentials or a path");
  return parsed.origin;
}

/** Server-side routing; neither an AI service key nor its internal origin reaches the browser. */
export function proxyRewrites(env: { API_ORIGIN?: string; AI_ORIGIN?: string }) {
  const backend = origin(env.API_ORIGIN ?? "https://company-corp.ru");
  const ai = env.AI_ORIGIN ? origin(env.AI_ORIGIN) : backend;
  const aiPrefix = env.AI_ORIGIN ? "" : "/ai";
  return {
    beforeFiles: [],
    afterFiles: [],
    fallback: [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      {
        source: "/ai/api/v1/runs/:runId/ws",
        destination: `${ai}${aiPrefix}/api/v1/runs/:runId/ws`,
      },
    ],
  };
}
