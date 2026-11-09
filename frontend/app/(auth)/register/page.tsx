import type { Metadata } from "next";
import { RegisterPage } from "@/_pages/register";
import { AuthGuard } from "@/shared/auth/auth-guard";

export const metadata: Metadata = { title: "Регистрация" };

export default function Page() {
  return (
    <AuthGuard require="guest">
      <RegisterPage />
    </AuthGuard>
  );
}
