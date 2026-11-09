import { cva } from "class-variance-authority";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-3 whitespace-nowrap font-sans font-normal select-none cursor-pointer transition-interaction outline-none focus-visible:inset-ring-[1.5px] focus-visible:inset-ring-accent-600 not-data-disabled:active:inset-ring-[1.5px] data-disabled:cursor-not-allowed [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-accent-400 text-special-100 not-data-disabled:hover:bg-accent-300 not-data-disabled:active:bg-accent-300 not-data-disabled:active:inset-ring-accent-600 data-disabled:bg-accent-200 data-disabled:text-content-400",
        secondary:
          "bg-transparent text-special-100 inset-ring-1 inset-ring-special-300 not-data-disabled:hover:bg-special-200 not-data-disabled:active:bg-special-200 data-disabled:text-special-300",
      },
      size: {
        sm: "h-10 rounded-sm px-4 py-2.5 text-body-sm [&_svg]:size-4.5",
        md: "h-12 rounded-md px-6 py-3 text-body-base [&_svg]:size-5",
        lg: "h-15 rounded-lg px-8 py-4 text-h6 [&_svg]:size-6",
      },
      iconOnly: { true: "", false: "" },
    },
    compoundVariants: [
      { variant: "secondary", size: "sm", className: "rounded-md" },
      {
        iconOnly: true,
        size: "sm",
        className: "size-10 rounded-md p-2.5 [&_svg]:size-5",
      },
      {
        iconOnly: true,
        size: "md",
        className: "size-12 p-3 [&_svg]:size-6",
      },
      {
        iconOnly: true,
        size: "lg",
        className: "size-15 p-4 [&_svg]:size-7",
      },
    ],
    defaultVariants: { variant: "primary", size: "md", iconOnly: false },
  },
);

export { buttonVariants };
