import type { ReactNode } from "react";
import { AuthGlass } from "@/shared/ui/auth-glass/auth-glass";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="grid min-h-dvh bg-content-0 lg:grid-cols-2">
      <div aria-hidden="true" className="hidden p-8 lg:block">
        <AuthGlass>
          <p className="absolute inset-x-[3.508772%] top-[65%] m-0 text-[6.2cqw] leading-[1.08] font-medium text-[#221a4c]">
            Факты вместо догадок
          </p>
          <p className="absolute inset-x-[3.508772%] bottom-[3.149606%] m-0 text-[2.4cqw] leading-[1.35] text-[#221a4c]/90">
            Betelgeuse сверяет ответы с документами закупки и подтверждает их
            цитатами из источников.
          </p>
        </AuthGlass>
      </div>
      <div className="flex items-center justify-center px-4 py-6 sm:p-8">
        {children}
      </div>
    </main>
  );
}
