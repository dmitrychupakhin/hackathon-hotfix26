"use client";

import { Combobox } from "@base-ui/react/combobox";
import { XMarkIcon } from "@heroicons/react/24/solid";
import { type ReactNode, useMemo, useState } from "react";
import selectorCheck from "@/shared/assets/img/icons/selector-check.svg";
import { cn } from "@/shared/utils/cn";
import { inputControlClasses, inputVariants } from "./input";

type DropdownOption = { value: string; label: string; disabled?: boolean };
type DropdownInputValue<Multiple> = Multiple extends true
  ? readonly string[]
  : string;
type DropdownOutputValue<Multiple> = Multiple extends true ? string[] : string;
type DropdownValue<Multiple> =
  | DropdownOutputValue<Multiple>
  | (Multiple extends true ? never : null);
type DropdownProps<Multiple extends boolean | undefined = false> = {
  options: readonly DropdownOption[];
  multiple?: Multiple;
  value?: DropdownInputValue<Multiple> | null;
  defaultValue?: DropdownInputValue<Multiple> | null;
  onValueChange?: (value: DropdownValue<Multiple>) => void;
  onSearchChange?: (query: string) => void;
  label?: string;
  placeholder?: string;
  emptyText?: string;
  className?: string;
  name?: string;
  form?: string;
  required?: boolean;
  disabled?: boolean;
  readOnly?: boolean;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
};

const panelClasses =
  "w-dropdown max-w-(--available-width) overflow-hidden rounded-xl bg-content-0 font-sans text-body-base font-normal text-content-900 shadow-context-menu ring-1 ring-context-menu-border outline-none data-closed:hidden";
const listClasses =
  "scrollbar-dropdown max-h-[min(var(--spacing-dropdown-height),var(--available-height))] overflow-y-auto py-3 pr-5 pl-3 outline-none";
const itemClasses =
  "group/dropdown-item flex h-10 min-w-0 cursor-default items-center rounded-md px-3 py-2 transition-interaction outline-none select-none data-disabled:cursor-not-allowed";
const singleClasses =
  "data-highlighted:bg-special-200 data-highlighted:text-accent-500 data-selected:text-accent-500 data-disabled:text-content-900 data-disabled:data-selected:text-content-900";
const check = (
  <span
    style={
      { "--selector-check": `url(${selectorCheck.src})` } as React.CSSProperties
    }
    className="block h-[11.4px] w-[13.2px] bg-current mask-(image:--selector-check) mask-contain mask-center mask-no-repeat"
  />
);

function checkbox(indicator: ReactNode) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex size-6 shrink-0 items-center justify-center rounded-[8px] text-special-100 inset-ring-1 inset-ring-special-300 transition-interaction group-data-highlighted/dropdown-item:inset-ring-accent-500 group-data-selected/dropdown-item:bg-accent-500 group-data-selected/dropdown-item:inset-ring-accent-500 group-data-disabled/dropdown-item:inset-ring-content-100 group-data-disabled/dropdown-item:text-special-302 group-data-disabled/dropdown-item:group-data-selected/dropdown-item:bg-accent-200 group-data-disabled/dropdown-item:group-data-selected/dropdown-item:inset-ring-0"
    >
      {indicator}
    </span>
  );
}

function highlightLabel(label: string, query: string): ReactNode {
  if (!query) return label;
  const parts: ReactNode[] = [];
  const normalized = label.toLocaleLowerCase();
  const needle = query.toLocaleLowerCase();
  let cursor = 0;
  let match = normalized.indexOf(needle);
  while (match !== -1) {
    parts.push(label.slice(cursor, match));
    parts.push(
      <span key={match} className="text-accent-500">
        {label.slice(match, match + query.length)}
      </span>,
    );
    cursor = match + query.length;
    match = normalized.indexOf(needle, cursor);
  }
  parts.push(label.slice(cursor));
  return parts;
}

function Dropdown<Multiple extends boolean | undefined = false>({
  options,
  multiple,
  label = "Поиск значения",
  placeholder = "Начните вводить",
  emptyText = "Ничего не найдено",
  className,
  open,
  defaultOpen = false,
  onOpenChange,
  onSearchChange,
  ...props
}: DropdownProps<Multiple>) {
  const [query, setQuery] = useState("");
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const values = useMemo(
    () => options.map((option) => option.value),
    [options],
  );
  const labels = useMemo(
    () => new Map(options.map((option) => [option.value, option.label])),
    [options],
  );

  function changeOpen(next: boolean) {
    if (open === undefined) setInternalOpen(next);
    onOpenChange?.(next);
  }

  return (
    <Combobox.Root<string, Multiple>
      {...props}
      multiple={multiple}
      items={values}
      itemToStringLabel={(value) => labels.get(value) ?? value}
      filter={(value, search) =>
        (labels.get(value) ?? value)
          .toLocaleLowerCase()
          .includes(search.trim().toLocaleLowerCase())
      }
      open={open ?? internalOpen}
      onOpenChange={changeOpen}
      onInputValueChange={(next) => {
        setQuery(next);
        onSearchChange?.(next);
      }}
    >
      <Combobox.InputGroup
        data-slot="dropdown-input"
        className={cn(
          inputVariants({ size: "md" }),
          multiple && "h-auto min-h-12 py-2",
        )}
      >
        {multiple ? (
          <Combobox.Value>
            {(selected: string[]) => (
              <Combobox.Chips
                aria-label={selected.length ? "Выбранные значения" : undefined}
                className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5"
              >
                {selected.map((value) => (
                  <Combobox.Chip
                    key={value}
                    aria-label={labels.get(value) ?? value}
                    aria-description="Нажмите Backspace или Delete, чтобы удалить"
                    className="flex max-w-full items-center gap-1 rounded-sm bg-special-200 py-1 pr-1 pl-2 text-body-sm text-content-900 outline-none focus-within:inset-ring-1 focus-within:inset-ring-accent-500"
                  >
                    <span className="truncate">
                      {labels.get(value) ?? value}
                    </span>
                    <Combobox.ChipRemove
                      aria-label={`Удалить ${labels.get(value) ?? value}`}
                      className="inline-flex shrink-0 cursor-pointer items-center rounded-sm text-special-302 outline-none focus-visible:inset-ring-1 focus-visible:inset-ring-accent-500 [&_svg]:size-4"
                    >
                      <XMarkIcon />
                    </Combobox.ChipRemove>
                  </Combobox.Chip>
                ))}
                <Combobox.Input
                  aria-label={label}
                  aria-description={
                    selected.length
                      ? "Для перехода к выбранным значениям нажмите стрелку влево в начале поля"
                      : undefined
                  }
                  placeholder={selected.length ? "" : placeholder}
                  className={cn(inputControlClasses, "h-6 w-auto min-w-16")}
                  onFocus={() => changeOpen(true)}
                  onChange={() => changeOpen(true)}
                />
              </Combobox.Chips>
            )}
          </Combobox.Value>
        ) : (
          <Combobox.Input
            aria-label={label}
            placeholder={placeholder}
            className={inputControlClasses}
            onFocus={() => changeOpen(true)}
            onChange={() => changeOpen(true)}
          />
        )}
        {query && !multiple ? (
          <Combobox.Clear
            aria-label="Очистить поле"
            className="inline-flex shrink-0 cursor-pointer items-center rounded-sm text-special-302 outline-none focus-visible:inset-ring-[1.5px] focus-visible:inset-ring-accent-600 [&_svg]:size-6"
          >
            <XMarkIcon />
          </Combobox.Clear>
        ) : null}
      </Combobox.InputGroup>
      <Combobox.Portal>
        <Combobox.Positioner
          side="bottom"
          align="start"
          sideOffset={4}
          className="isolate outline-none"
        >
          <Combobox.Popup
            data-slot="dropdown"
            className={cn(
              panelClasses,
              "min-w-[min(var(--anchor-width),var(--available-width))]",
              className,
            )}
          >
            <Combobox.Empty className="px-6 py-3 text-content-500">
              {emptyText}
            </Combobox.Empty>
            <Combobox.List aria-label={label} className={listClasses}>
              {(value: string) => {
                const option = options.find((option) => option.value === value);
                if (!option) return null;
                return (
                  <Combobox.Item
                    key={value}
                    value={value}
                    disabled={option.disabled}
                    className={cn(
                      itemClasses,
                      multiple ? "gap-3" : singleClasses,
                    )}
                  >
                    {multiple
                      ? checkbox(
                          <Combobox.ItemIndicator>
                            {check}
                          </Combobox.ItemIndicator>,
                        )
                      : null}
                    <span className="min-w-0 flex-1 truncate">
                      {highlightLabel(option.label, query.trim())}
                    </span>
                  </Combobox.Item>
                );
              }}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  );
}

export { Dropdown, type DropdownProps, type DropdownOption };
