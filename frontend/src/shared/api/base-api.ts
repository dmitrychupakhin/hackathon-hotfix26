import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import { isProtectedPath, loginPath } from "@/shared/auth/navigation";

const rawBaseQuery = fetchBaseQuery({ baseUrl: "/", credentials: "include" });

let refreshPromise: ReturnType<typeof rawBaseQuery> | undefined;
let refreshGeneration = 0;
const statusOf = (result: Awaited<ReturnType<typeof rawBaseQuery>>) =>
  result.error?.status === "PARSING_ERROR"
    ? result.error.originalStatus
    : result.error?.status;

export const baseApi = createApi({
  reducerPath: "api",
  baseQuery: async (args, api, extraOptions) => {
    const generation = refreshGeneration;
    if (refreshPromise) await refreshPromise;
    let result = await rawBaseQuery(args, api, extraOptions);
    const url = typeof args === "string" ? args : args.url;
    const excluded =
      /^\/?api\/users\/(login|logout|refresh|vk\/login)\/?$/.test(url);
    let status = statusOf(result);
    if (status === 401 && !excluded) {
      if (generation === refreshGeneration) {
        if (!refreshPromise) {
          refreshPromise = Promise.resolve(
            rawBaseQuery(
              { url: "/api/users/refresh", method: "POST", body: {} },
              { ...api, signal: new AbortController().signal },
              extraOptions,
            ),
          )
            .then((response) => {
              if (!response.error) refreshGeneration++;
              return response;
            })
            .finally(() => {
              refreshPromise = undefined;
            });
        }
        const refreshed = await refreshPromise!;
        if (refreshed.error) {
          if (statusOf(refreshed) !== 401 && statusOf(refreshed) !== 403)
            return refreshed;
        } else {
          result = await rawBaseQuery(args, api, extraOptions);
        }
      } else {
        result = await rawBaseQuery(args, api, extraOptions);
      }
      status = statusOf(result);
    }

    if (
      status === 401 &&
      !excluded &&
      typeof window !== "undefined" &&
      isProtectedPath(window.location.pathname)
    ) {
      window.location.replace(
        loginPath(
          window.location.pathname +
            window.location.search +
            window.location.hash,
        ),
      );
    }

    return result;
  },
  tagTypes: [
    "CurrentUser",
    "User",
    "Chat",
    "ChatMessages",
    "ChatFiles",
    "ChatRun",
    "Comparison",
  ],
  keepUnusedDataFor: 60,
  refetchOnFocus: true,
  refetchOnReconnect: true,
  endpoints: () => ({}),
});
