import type { ChatRead } from "@/shared/api/chats";
export function ChatHeader({
  chat,
  fileCount,
}: {
  chat: ChatRead;
  fileCount?: number;
}) {
  return (
    <header className="min-h-16 shrink-0">
      <h2 className="break-words text-h5 font-medium">
        {chat.title || "Без названия"}
      </h2>
      <p className="mt-1 text-label-md text-content-500">
        Обсуждение
        {fileCount !== undefined
          ? ` · ${fileCount} ${fileCount % 10 === 1 && fileCount % 100 !== 11 ? "файл" : fileCount % 10 >= 2 && fileCount % 10 <= 4 && (fileCount % 100 < 12 || fileCount % 100 > 14) ? "файла" : "файлов"} в контексте`
          : ""}
      </p>
    </header>
  );
}
