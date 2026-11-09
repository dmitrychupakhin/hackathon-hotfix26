import type { Metadata } from "next";
import { PasswordRecoveryPage } from "@/_pages/password-recovery";

export const metadata: Metadata = { title: "Восстановление пароля" };

export default function Page() {
  return <PasswordRecoveryPage />;
}
