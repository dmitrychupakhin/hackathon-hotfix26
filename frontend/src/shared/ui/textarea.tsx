import type { ComponentProps } from "react";
import { cn } from "@/shared/utils/cn";

function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "w-full min-w-0 resize-y rounded-xl border border-special-300 bg-dom-light px-4 py-3 font-sans text-body-base text-content-900 outline-none placeholder:text-special-302 focus-visible:border-accent-600 focus-visible:ring-1 focus-visible:ring-accent-600 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
