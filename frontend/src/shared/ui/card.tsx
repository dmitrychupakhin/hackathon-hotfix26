import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/shared/utils/cn";

const cardVariants = cva("min-w-0 text-content-900", {
  variants: {
    variant: {
      default: "bg-content-0",
      neutral: "bg-dom-light",
      accent: "bg-accent-100",
    },
    padding: {
      none: "p-0",
      sm: "px-6 py-5",
      md: "p-6",
      lg: "p-8",
      wide: "px-11 py-8",
    },
    radius: {
      md: "rounded-2xl",
      lg: "rounded-3xl",
    },
    bordered: {
      true: "inset-ring-1 inset-ring-special-300",
    },
  },
  defaultVariants: {
    variant: "default",
    padding: "lg",
    radius: "lg",
    bordered: false,
  },
});

type CardProps = ComponentProps<"div"> & VariantProps<typeof cardVariants>;

function Card({
  variant,
  padding,
  radius,
  bordered,
  className,
  ...props
}: CardProps) {
  return (
    <div
      data-slot="card"
      className={cn(
        cardVariants({ variant, padding, radius, bordered }),
        className,
      )}
      {...props}
    />
  );
}

export { Card, type CardProps };
