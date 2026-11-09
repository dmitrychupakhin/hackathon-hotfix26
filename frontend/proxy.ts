import { NextResponse, type NextRequest } from "next/server";
import { hasValidSession } from "@/shared/api/account/session.server";
import { createClient } from "@/shared/api/__generated__/auth/sdk/client";
import { usersRefreshCreate } from "@/shared/api/__generated__/auth/sdk/sdk.gen";
import { createServerFetch, ServerApiError } from "@/shared/api/server-transport";
import { isProtectedPath, loginPath, safeReturnPath } from "@/shared/auth/navigation";

export async function proxy(request: NextRequest) {
  let authenticated = request.cookies.has("access") && await hasValidSession(request.cookies.toString());
  let refreshed: Response | undefined;
  if (!authenticated && request.cookies.has("refresh")) {
    const origin = new URL(process.env.API_ORIGIN ?? "https://company-corp.ru").origin;
    const client = createClient({
      baseUrl: origin,
      fetch: createServerFetch(origin, request.cookies.toString(), globalThis.fetch),
      throwOnError: true,
    });
    try {
      const result = await usersRefreshCreate({ client, body: {}, throwOnError: true });
      refreshed = result.response;
      const cookies = new NextResponse(null, { headers: refreshed.headers }).cookies;
      for (const cookie of cookies.getAll()) request.cookies.set(cookie.name, cookie.value);
      authenticated = true;
    } catch (error) {
      if (!(error instanceof ServerApiError) || ![401, 403].includes(error.status)) throw error;
    }
  }
  const protectedPage = isProtectedPath(request.nextUrl.pathname);
  const guestPage = ["/login", "/register"].includes(request.nextUrl.pathname);
  const response = protectedPage && !authenticated
    ? NextResponse.redirect(new URL(loginPath(request.nextUrl.pathname + request.nextUrl.search), request.url))
    : guestPage && authenticated
      ? NextResponse.redirect(new URL(safeReturnPath(request.nextUrl.searchParams.get("next")), request.url))
      : NextResponse.next({ request: { headers: request.headers } });
  for (const cookie of refreshed?.headers.getSetCookie() ?? []) response.headers.append("Set-Cookie", cookie);
  return response;
}

export const config = { matcher: [
  "/profile/:path*", "/chats/:path*", "/prompt/:path*", "/comparisons/:path*",
  "/change-email/:path*", "/change-password/:path*", "/login", "/register",
] };
