"use client";

import { Radio } from "@base-ui/react/radio";
import { type ReactNode, useId } from "react";
import { cn } from "@/shared/utils/cn";

type RadioButtonProps = Omit<
  Radio.Root.Props<string>,
  "children" | "className"
> & {
  label?: ReactNode;
  className?: string;
};

function RadioButton({ label, className, id, ...props }: RadioButtonProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const control = (
    <Radio.Root
      {...props}
      id={controlId}
      data-slot="radio-button"
      className={cn(
        "inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-full text-special-100 outline-none inset-ring-1 inset-ring-special-300 transition-interaction data-checked:bg-accent-400 data-checked:inset-ring-0 not-data-disabled:not-data-readonly:hover:inset-ring-accent-400 not-data-disabled:not-data-readonly:data-checked:hover:bg-accent-300 not-data-disabled:not-data-readonly:data-checked:hover:inset-ring-[0.5px] not-data-disabled:not-data-readonly:data-checked:hover:inset-ring-accent-500 focus-visible:inset-ring-[1.5px] focus-visible:inset-ring-accent-600 data-disabled:cursor-not-allowed data-disabled:inset-ring-content-100 data-disabled:text-special-302 data-disabled:data-checked:bg-accent-200 data-disabled:data-checked:inset-ring-0",
        className,
      )}
    >
      <Radio.Indicator className="block size-[9.6px] rounded-full bg-current" />
    </Radio.Root>
  );

  return label != null ? (
    <label
      htmlFor={controlId}
      className="inline-flex w-fit items-center gap-3 font-sans text-body-base font-normal text-content-900 has-[[data-disabled][data-unchecked]]:text-content-500"
    >
      {control}
      <span>{label}</span>
    </label>
  ) : (
    control
  );
}

export { RadioButton, type RadioButtonProps };
