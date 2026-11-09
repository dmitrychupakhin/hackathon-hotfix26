import { Profile } from "@/_pages/profile";
import { AuthGuard } from "@/shared/auth/auth-guard";

export default function Page() {
  return (
    <AuthGuard require="authenticated">
      <Profile />
    </AuthGuard>
  );
}
