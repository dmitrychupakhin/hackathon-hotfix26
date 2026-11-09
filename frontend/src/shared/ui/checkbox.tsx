"use client";

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";
import { type ReactNode, useId } from "react";
import selectorCheck from "@/shared/assets/img/icons/selector-check.svg";
import { cn } from "@/shared/utils/cn";

type CheckboxProps = Omit<
  CheckboxPrimitive.Root.Props,
  "children" | "className"
> & {
  label?: ReactNode;
  className?: string;
};

function Checkbox({ label, className, id, ...props }: CheckboxProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const control = (
    <CheckboxPrimitive.Root
      {...props}
      id={controlId}
      data-slot="checkbox"
      className={cn(
        "inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-[8px] text-special-100 outline-none inset-ring-1 inset-ring-special-300 transition-interaction data-checked:bg-accent-400 data-checked:inset-ring-accent-400 data-indeterminate:bg-accent-400 data-indeterminate:inset-ring-accent-400 not-data-disabled:not-data-readonly:hover:inset-ring-accent-400 not-data-disabled:not-data-readonly:data-checked:hover:bg-accent-300 not-data-disabled:not-data-readonly:data-checked:hover:inset-ring-[0.5px] not-data-disabled:not-data-readonly:data-checked:hover:inset-ring-accent-500 focus-visible:inset-ring-[1.5px] focus-visible:inset-ring-accent-600 data-disabled:cursor-not-allowed data-disabled:inset-ring-content-100 data-disabled:text-special-302 data-disabled:data-checked:bg-accent-200 data-disabled:data-checked:inset-ring-0 data-disabled:data-indeterminate:bg-accent-200 data-disabled:data-indeterminate:inset-ring-0",
        className,
      )}
    >
      <CheckboxPrimitive.Indicator className="group/indicator inline-flex items-center justify-center">
        <span
          aria-hidden="true"
          style={
            {
              "--selector-check": `url(${selectorCheck.src})`,
            } as React.CSSProperties
          }
          className="block h-[11.4px] w-[13.2px] bg-current mask-(image:--selector-check) mask-contain mask-center mask-no-repeat group-data-indeterminate/indicator:hidden"
        />
        <span
          aria-hidden="true"
          className="hidden h-0.5 w-3 rounded-full bg-current group-data-indeterminate/indicator:block"
        />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
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

export { Checkbox, type CheckboxProps };
