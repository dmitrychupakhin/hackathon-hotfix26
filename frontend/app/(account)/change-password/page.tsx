import { ChangePasswordPage } from "@/_pages/change-password";
import { AuthGuard } from "@/shared/auth/auth-guard";

export default function Page() {
  return (
    <AuthGuard require="authenticated">
      <ChangePasswordPage />
    </AuthGuard>
  );
}
