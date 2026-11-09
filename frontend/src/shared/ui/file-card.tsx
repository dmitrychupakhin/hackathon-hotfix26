import { DocumentIcon } from "@heroicons/react/24/outline";

export function FileCard({ name, detail }: { name: string; detail: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-content-100 px-3 py-2">
      <span className="flex size-[30px] shrink-0 items-center justify-center rounded-[10px] bg-accent-100 text-accent-600">
        <DocumentIcon className="size-4" />
      </span>
      <div>
        <p className="text-[13px] leading-[19px] font-medium">{name}</p>
        <p className="text-[11px] leading-4 text-content-500">{detail}</p>
      </div>
    </div>
  );
}
