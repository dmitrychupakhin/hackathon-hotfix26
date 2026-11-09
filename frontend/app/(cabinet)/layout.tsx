import type { ReactNode } from "react";
import { CabinetLayout } from "@/_app/layouts/cabinet-layout";
import { AuthGuard } from "@/shared/auth/auth-guard";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard require="authenticated">
      <CabinetLayout>{children}</CabinetLayout>
    </AuthGuard>
  );
}
