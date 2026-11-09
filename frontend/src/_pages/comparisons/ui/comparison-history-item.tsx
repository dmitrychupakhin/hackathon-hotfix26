export function ComparisonHistoryItem({
  title,
  status,
  active,
  onSelect,
}: {
  title: string;
  status: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={`w-full rounded-xl p-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-accent-600 ${active ? "bg-accent-100" : "hover:bg-content-50"}`}
    >
      <span className="block text-body-sm leading-6">{title}</span>
      <span className="block text-[10px] leading-3 text-content-500">
        {status}
      </span>
    </button>
  );
}
