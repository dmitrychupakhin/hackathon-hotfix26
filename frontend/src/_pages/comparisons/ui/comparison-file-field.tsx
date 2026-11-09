import { useId, useRef } from "react";
import { Button } from "@/shared/ui/button";
import { FileCard } from "@/shared/ui/file-card";
import { comparisonAccept } from "../model/comparison";
export function ComparisonFileField({
  label,
  accept = comparisonAccept,
  files,
  multiple,
  disabled,
  error,
  onChange,
}: {
  label: string;
  accept?: string;
  files: File[];
  multiple?: boolean;
  disabled: boolean;
  error?: string;
  onChange: (files: File[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const errorId = useId();
  return (
    <>
      <input
        ref={input}
        type="file"
        aria-label={label}
        aria-invalid={!!error}
        aria-describedby={error ? errorId : undefined}
        className="hidden"
        multiple={multiple}
        accept={accept}
        disabled={disabled}
        onChange={(event) => {
          const selected = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (selected.length)
            onChange(multiple ? [...files, ...selected] : selected.slice(0, 1));
        }}
      />
      {files.map((file, index) => (
        <div
          key={`${index}-${file.name}-${file.size}-${file.lastModified}`}
          className="flex min-w-0 flex-col gap-1 [overflow-wrap:anywhere]"
        >
          <FileCard
            name={file.name}
            detail={`${(file.size / 1024 / 1024).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} МиБ`}
          />
          <button
            type="button"
            disabled={disabled}
            aria-label={`Убрать ${file.name}`}
            className="self-start rounded-md px-2 py-1 text-body-sm text-content-500 outline-none hover:bg-accent-100 focus-visible:outline-2 focus-visible:outline-accent-600 disabled:opacity-50"
            onClick={() => onChange(files.filter((_file, i) => i !== index))}
          >
            Убрать
          </button>
        </div>
      ))}
      <Button
        type="button"
        variant="secondary"
        disabled={disabled}
        aria-label={`${files.length ? (multiple ? "Добавить" : "Заменить") : "Загрузить"}: ${label}`}
        aria-describedby={error ? errorId : undefined}
        onClick={() => input.current?.click()}
      >
        {multiple
          ? files.length
            ? "Добавить ещё файлы"
            : "Добавить документы"
          : files.length
            ? "Заменить файл"
            : "Загрузить файл"}
      </Button>
      {error && (
        <p id={errorId} role="alert" className="text-body-sm text-error-600">
          {error}
        </p>
      )}
    </>
  );
}
