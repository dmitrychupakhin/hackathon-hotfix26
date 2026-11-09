"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "@heroicons/react/20/solid";
import { cn } from "@/shared/utils/cn";

type PaginationProps = {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
};

const itemClasses =
  "inline-flex size-9 shrink-0 items-center justify-center rounded-md bg-special-200 text-body-base text-content-900 inset-ring-1 inset-ring-special-300 transition-interaction outline-none hover:bg-content-0 hover:text-accent-400 hover:inset-ring-accent-400 focus-visible:inset-ring-[1.5px] focus-visible:inset-ring-accent-500 disabled:cursor-not-allowed disabled:bg-content-0 disabled:text-special-300 disabled:inset-ring-special-300";

function Pagination({
  page,
  totalPages,
  onPageChange,
  className,
}: PaginationProps) {
  const total = Math.max(0, Math.floor(totalPages));
  if (!total) return null;
  const current = Math.max(1, Math.min(total, Math.floor(page) || 1));
  const visible = new Set([1, total, current - 1, current, current + 1]);
  if (current <= 3)
    for (let i = 1; i <= Math.min(4, total); i++) visible.add(i);
  if (current >= total - 2)
    for (let i = Math.max(1, total - 3); i <= total; i++) visible.add(i);
  const pages = [...visible]
    .filter((n) => n >= 1 && n <= total)
    .sort((a, b) => a - b);
  const items: (number | string)[] = [];
  for (const [index, value] of pages.entries()) {
    const previous = pages[index - 1];
    if (previous !== undefined && value - previous === 2)
      items.push(previous + 1);
    else if (previous !== undefined && value - previous > 2)
      items.push(`gap-${value}`);
    items.push(value);
  }
  return (
    <nav
      aria-label="Навигация по страницам"
      className={cn(
        "flex max-w-full items-center gap-3 overflow-x-auto",
        className,
      )}
    >
      <button
        type="button"
        className={itemClasses}
        aria-label="Предыдущая страница"
        disabled={current === 1}
        onClick={() => onPageChange(current - 1)}
      >
        <ChevronLeftIcon className="size-6" />
      </button>
      {items.map((item) =>
        typeof item === "number" ? (
          <button
            key={item}
            type="button"
            aria-label={`Страница ${item}`}
            aria-current={item === current ? "page" : undefined}
            className={cn(
              itemClasses,
              item === current &&
                "bg-accent-100 text-accent-400 inset-ring-accent-400 hover:bg-accent-100",
            )}
            onClick={() => onPageChange(item)}
          >
            {item}
          </button>
        ) : (
          <span key={item} aria-hidden="true" className={itemClasses}>
            ...
          </span>
        ),
      )}
      <button
        type="button"
        className={itemClasses}
        aria-label="Следующая страница"
        disabled={current === total}
        onClick={() => onPageChange(current + 1)}
      >
        <ChevronRightIcon className="size-6" />
      </button>
    </nav>
  );
}

export { Pagination, type PaginationProps };
