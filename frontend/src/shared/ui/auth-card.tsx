import type { ReactNode } from "react";
import { Card } from "@/shared/ui/card";

type AuthCardProps = {
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
};

export function AuthCard({
  title,
  description,
  children,
  footer,
}: AuthCardProps) {
  return (
    <Card className="flex w-full max-w-[480px] flex-col gap-8 p-5 sm:p-8">
      <header className="text-special-100">
        <h1 className="text-h5 font-medium sm:text-h3">{title}</h1>
        <p>{description}</p>
      </header>
      <div className="flex flex-col gap-4">{children}</div>
      <footer className="flex flex-col gap-4 text-center text-special-100">
        {footer}
      </footer>
    </Card>
  );
}
