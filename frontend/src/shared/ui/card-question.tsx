import { MinusIcon, PlusIcon } from "@heroicons/react/16/solid";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/shared/utils/cn";

type CardQuestionProps = Omit<ComponentProps<"details">, "children"> & {
  question: ReactNode;
  children: ReactNode;
};

function CardQuestion({
  question,
  children,
  className,
  ...props
}: CardQuestionProps) {
  return (
    <details
      data-slot="card-question"
      className={cn(
        "group w-full min-w-0 rounded-3xl bg-accent-100 p-6 open:bg-content-0 open:inset-ring-1 open:inset-ring-[#e6ece6]",
        className,
      )}
      {...props}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2.5 text-h3 font-medium text-special-100 outline-offset-4 focus-visible:outline-2 focus-visible:outline-accent-600 [&::-webkit-details-marker]:hidden">
        <span>{question}</span>
        <span
          className="flex size-9 shrink-0 items-center justify-center rounded-full bg-content-0 text-[#0f172a] group-open:bg-accent-100"
          aria-hidden="true"
        >
          <PlusIcon className="size-4 group-open:hidden" />
          <MinusIcon className="hidden size-4 group-open:block" />
        </span>
      </summary>
      <div className="pt-6 text-body-base font-normal text-content-700">
        {children}
      </div>
    </details>
  );
}

export { CardQuestion, type CardQuestionProps };
