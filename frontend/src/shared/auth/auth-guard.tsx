import "server-only";

import { redirect } from "next/navigation";
import { type ReactNode, Suspense } from "react";
import { isAuthenticated } from "./session.server";

type AuthGuardProps = {
  children: ReactNode;
  require: "authenticated" | "guest";
};

async function CheckSession({ children, require: access }: AuthGuardProps) {
  const authenticated = await isAuthenticated();
  if (access === "authenticated" && !authenticated) redirect("/login");
  if (access === "guest" && authenticated) redirect("/profile");
  return children;
}

export function AuthGuard(props: AuthGuardProps) {
  return (
    <Suspense fallback={null}>
      <CheckSession {...props} />
    </Suspense>
  );
}
