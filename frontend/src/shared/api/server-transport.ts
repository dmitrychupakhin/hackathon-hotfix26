import "server-only";

/** Settings owned by the request-scoped transport, not by individual calls. */
export type ServerOptions<T> = Omit<
  T,
  | "client"
  | "baseUrl"
  | "fetch"
  | "throwOnError"
  | "cache"
  | "next"
  | "parseAs"
  | "requestValidator"
  | "responseValidator"
  | "responseTransformer"
>;

export class ServerApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`Backend request failed with HTTP ${status}`);
    this.name = "ServerApiError";
  }
}

export function createServerFetch(
  origin: string,
  cookieHeader: string,
  fetchImplementation: typeof fetch,
): typeof fetch {
  return async (input, init) => {
    const url = new URL(
      input instanceof Request ? input.url : input.toString(),
    );
    if (url.origin !== origin)
      throw new Error("Server API requests must use API_ORIGIN");
    const headers = new Headers(
      init?.headers ?? (input instanceof Request ? input.headers : undefined),
    );
    headers.delete("Cookie");
    if (cookieHeader) headers.set("Cookie", cookieHeader);
    const response = await fetchImplementation(input, {
      ...init,
      headers,
      cache: "no-store",
      redirect: "manual",
    });
    if (!response.ok) {
      const text = await response.text();
      let body: unknown = text;
      try {
        body = JSON.parse(text);
      } catch {
        /* Preserve non-JSON error bodies. */
      }
      throw new ServerApiError(response.status, body);
    }
    return response;
  };
}
