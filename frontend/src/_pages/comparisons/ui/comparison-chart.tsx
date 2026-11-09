import { ComparisonCard } from "./comparison-card";
export function ComparisonChart({
  title,
  rows,
  max = 100,
  percentage = false,
}: {
  title: string;
  rows: readonly (readonly [string, number | null, number | null])[];
  max?: number;
  percentage?: boolean;
}) {
  const width = (value: number | null) =>
    `${Math.min(100, Math.max(0, ((value ?? 0) / Math.max(1, max)) * 100))}%`;
  const format = (value: number | null) =>
    value === null
      ? "Н/Д"
      : `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}${percentage ? "%" : ""}`;
  return (
    <ComparisonCard title={title}>
      <p className="text-label-md text-content-500">
        Baseline — зелёный · Harness — фиолетовый
      </p>
      {rows.length === 0 && (
        <p className="text-body-sm text-content-500">
          Нет данных по категориям.
        </p>
      )}
      {rows.map(([label, a, b]) => (
        <div
          key={label}
          className="grid min-w-0 grid-cols-[minmax(60px,90px)_minmax(0,1fr)_auto] items-center gap-3 text-label-md"
        >
          <span className="break-words">{label}</span>
          <div aria-hidden="true" className="flex min-w-0 flex-col gap-1">
            <div
              className="h-2 rounded bg-accent-500"
              style={{ width: width(a) }}
            />
            <div
              className="h-2 rounded bg-[#7c3aed]"
              style={{ width: width(b) }}
            />
          </div>
          <span>
            {format(a)} / {format(b)}
          </span>
        </div>
      ))}
    </ComparisonCard>
  );
}
