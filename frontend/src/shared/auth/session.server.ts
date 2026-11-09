import "server-only";

import { cookies } from "next/headers";
import { cache } from "react";
import { hasValidSession } from "@/shared/api/account/session.server";

export const isAuthenticated = cache(async () => {
  const cookieStore = await cookies();
  return cookieStore.has("access") && hasValidSession(cookieStore.toString());
});
