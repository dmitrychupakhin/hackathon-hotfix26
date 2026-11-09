import type { ReactNode } from "react";

export function AccountLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-6 sm:py-8">
      {children}
    </main>
  );
}
