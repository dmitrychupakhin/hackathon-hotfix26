import { ChangeEmailPage } from "@/_pages/change-email";
import { AuthGuard } from "@/shared/auth/auth-guard";

export default function Page() {
  return (
    <AuthGuard require="authenticated">
      <ChangeEmailPage />
    </AuthGuard>
  );
}
