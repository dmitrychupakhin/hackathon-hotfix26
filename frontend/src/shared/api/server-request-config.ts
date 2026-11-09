import "server-only";
import { cookies } from "next/headers";
import { createServerFetch } from "./server-transport";

export async function getServerRequestConfig() {
  const baseUrl = new URL(process.env.API_ORIGIN ?? "https://company-corp.ru")
    .origin;
  const cookieHeader = (await cookies()).toString();
  return {
    baseUrl,
    throwOnError: true as const,
    cache: "no-store" as const,
    fetch: createServerFetch(baseUrl, cookieHeader, globalThis.fetch),
  };
}
