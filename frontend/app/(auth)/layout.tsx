import type { ReactNode } from "react";
import { AuthLayout } from "@/_app/layouts";
import { AuthGuard } from "@/shared/auth/auth-guard";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard require="guest">
      <AuthLayout>{children}</AuthLayout>
    </AuthGuard>
  );
}
