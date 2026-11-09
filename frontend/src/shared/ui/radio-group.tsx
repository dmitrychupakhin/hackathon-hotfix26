"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group";
import { cva } from "class-variance-authority";
import { createContext, type ReactElement, useContext } from "react";
import { cn } from "@/shared/utils/cn";

type RadioGroupSize = "sm" | "md" | "lg";
const RadioGroupSizeContext = createContext<RadioGroupSize>("md");

type RadioGroupProps = Omit<RadioGroupPrimitive.Props<string>, "className"> & {
  variant?: "default" | "segmented";
  size?: RadioGroupSize;
  className?: string;
};

function RadioGroup({
  variant = "default",
  size = "md",
  className,
  ...props
}: RadioGroupProps) {
  return (
    <RadioGroupSizeContext value={size}>
      <RadioGroupPrimitive
        {...props}
        data-slot="radio-group"
        data-variant={variant}
        className={cn(
          variant === "segmented"
            ? "flex w-fit max-w-full"
            : "flex flex-col gap-3",
          className,
        )}
      />
    </RadioGroupSizeContext>
  );
}

const radioGroupItemVariants = cva(
  "relative inline-flex shrink-0 cursor-pointer items-center justify-center whitespace-nowrap bg-content-0 font-sans font-normal text-content-900 outline-none transition-interaction before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:border-y-[1.5px] before:border-special-300 before:transition-interaction first-of-type:before:border-l-[1.5px] last-of-type:before:border-r-[1.5px] only-of-type:before:border-x-[1.5px] data-checked:bg-accent-200 data-checked:text-special-100 data-checked:before:border-accent-400 not-data-disabled:not-data-readonly-of-type:hover:bg-accent-200 not-data-disabled:not-data-readonly-of-type:hover:text-special-100 focus-visible:inset-ring-[1.5px] focus-visible:inset-ring-accent-600 data-disabled:cursor-not-allowed data-disabled:text-content-500 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      size: {
        sm: "h-9 gap-1 px-3 text-body-sm first-of-type:rounded-l-sm last-of-type:rounded-r-sm [&_svg]:size-4",
        md: "h-12 gap-1.5 px-4 text-body-base first-of-type:rounded-l-md last-of-type:rounded-r-md [&_svg]:size-5",
        lg: "h-13 gap-1.5 px-4 text-h6 first-of-type:rounded-l-lg last-of-type:rounded-r-lg [&_svg]:size-5.5",
      },
    },
  },
);

type RadioGroupItemProps = Omit<Radio.Root.Props<string>, "className"> & {
  icon?: ReactElement;
  iconPosition?: "left" | "right";
  className?: string;
};

function RadioGroupItem({
  icon,
  iconPosition = "left",
  children,
  className,
  ...props
}: RadioGroupItemProps) {
  const size = useContext(RadioGroupSizeContext);
  const iconContent = icon ? (
    <span aria-hidden="true" className="inline-flex">
      {icon}
    </span>
  ) : null;
  return (
    <Radio.Root
      {...props}
      data-slot="radio-group-item"
      className={cn(radioGroupItemVariants({ size }), className)}
    >
      {iconPosition === "left" ? iconContent : null}
      {children}
      {iconPosition === "right" ? iconContent : null}
    </Radio.Root>
  );
}

export {
  RadioGroup,
  RadioGroupItem,
  type RadioGroupProps,
  type RadioGroupItemProps,
};
