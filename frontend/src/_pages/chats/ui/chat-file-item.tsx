import type { ChatFileRead } from "@/shared/api/chats";
import { FileCard } from "@/shared/ui/file-card";
import { ChatItemMenu } from "./chat-item-menu";

function fileDetail(file: ChatFileRead) {
  const format = file.name.split(".").at(-1)?.toUpperCase() || "ФАЙЛ";
  const isMegabytes = file.size >= 1024 * 1024;
  const size = file.size / (isMegabytes ? 1024 * 1024 : 1024);
  return `${format} · ${size.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} ${isMegabytes ? "МБ" : "КБ"}`;
}
export function ChatFileItem({
  file,
  deleting,
  onDelete,
  onPreview,
}: {
  file: ChatFileRead;
  deleting: boolean;
  onDelete: () => void;
  onPreview: () => void;
}) {
  return (
    <div className="group relative min-w-0" title={file.name}>
      <div className="[&>div>div]:min-w-0 [&>div>div]:flex-1 [&>div>div]:pr-5 [&_p]:truncate">
        <FileCard name={file.name} detail={fileDetail(file)} />
      </div>
      <div className="absolute top-1/2 right-1 -translate-y-1/2">
        <ChatItemMenu
          label={`Действия файла «${file.name}»`}
          items={[
            {
              id: "open",
              label: "Открыть",
              onSelect: onPreview,
            },
            {
              id: "delete",
              label: "Удалить",
              variant: "destructive",
              disabled: deleting,
              onSelect: onDelete,
            },
          ]}
        />
      </div>
    </div>
  );
}
