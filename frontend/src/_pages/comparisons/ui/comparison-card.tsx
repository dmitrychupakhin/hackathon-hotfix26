import type { ReactNode } from "react";
export function ComparisonCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-special-300 p-5">
      <h3 className="text-body-lg leading-7 font-medium">{title}</h3>
      {children}
    </section>
  );
}
