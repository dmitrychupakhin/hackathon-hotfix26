import type { Metadata } from "next";
import { LoginPage } from "@/_pages/login";
import { AuthGuard } from "@/shared/auth/auth-guard";

export const metadata: Metadata = { title: "Вход" };

export default function Page() {
  return (
    <AuthGuard require="guest">
      <LoginPage />
    </AuthGuard>
  );
}
