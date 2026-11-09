"use client";

import { Switch } from "@base-ui/react/switch";
import { type ReactNode, useId } from "react";
import { cn } from "@/shared/utils/cn";

type ToggleProps = Omit<Switch.Root.Props, "children" | "className"> & {
  label?: ReactNode;
  className?: string;
};

// Figma calls this Toggle; its on/off semantics correspond to a switch.
function Toggle({ label, className, id, ...props }: ToggleProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const control = (
    <Switch.Root
      {...props}
      id={controlId}
      data-slot="toggle"
      className={cn(
        "group/toggle relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full bg-content-200 p-0.5 outline-none transition-interaction data-checked:bg-accent-400 not-data-disabled:not-data-readonly:hover:inset-ring-[0.5px] not-data-disabled:not-data-readonly:hover:inset-ring-accent-400 not-data-disabled:not-data-readonly:data-checked:hover:bg-accent-300 not-data-disabled:not-data-readonly:data-checked:hover:inset-ring-accent-500 focus-visible:inset-ring-[1.5px] focus-visible:inset-ring-accent-600 data-disabled:cursor-not-allowed data-disabled:bg-content-100 data-disabled:data-checked:bg-accent-200",
        className,
      )}
    >
      <Switch.Thumb className="pointer-events-none block size-6 rounded-full bg-content-0 transition-transform duration-(--motion-duration-interaction) ease-(--ease-interaction) motion-reduce:transition-none data-checked:translate-x-5 data-checked:shadow-selector-thumb group-hover/toggle:shadow-selector-thumb data-disabled:shadow-selector-thumb-disabled" />
    </Switch.Root>
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

export { Toggle, type ToggleProps };
