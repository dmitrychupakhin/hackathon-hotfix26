import "server-only";

import { createClient } from "../__generated__/account/sdk/client";
import { usersMeRetrieve } from "../__generated__/account/sdk/sdk.gen";
import { createServerFetch, ServerApiError } from "../server-transport";

export async function hasValidSession(cookieHeader: string) {
  const origin = new URL(process.env.API_ORIGIN ?? "https://company-corp.ru")
    .origin;
  const client = createClient({
    baseUrl: origin,
    fetch: createServerFetch(origin, cookieHeader, globalThis.fetch),
    cache: "no-store",
    throwOnError: true,
  });
  try {
    await usersMeRetrieve({ client, throwOnError: true });
    return true;
  } catch (error) {
    if (
      error instanceof ServerApiError &&
      (error.status === 401 || error.status === 403)
    )
      return false;
    throw error;
  }
}
