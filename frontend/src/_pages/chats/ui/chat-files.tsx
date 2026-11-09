import { CloudArrowDownIcon, FolderIcon } from "@heroicons/react/24/outline";
import { type ChangeEvent, useId, useRef, useState } from "react";
import {
  useChatFilesInfiniteQuery,
  useChatsFilesCreateMutation,
  useChatsFilesDestroyMutation,
} from "@/shared/api/chats";
import type { PreviewSelection } from "@/shared/api/chats/document-preview-api";
import { Button } from "@/shared/ui/button";
import { chatError } from "../model/chat-utils";
import { ChatFeedback, ChatLoadMore } from "./chat-feedback";
import { ChatFileItem } from "./chat-file-item";
export function ChatFiles({
  chatId,
  running,
  onPreview,
}: {
  chatId: string;
  running: boolean;
  onPreview: (selection: PreviewSelection) => void;
}) {
  const [error, setError] = useState("");
  const query = useChatFilesInfiniteQuery(chatId);
  const [upload, uploading] = useChatsFilesCreateMutation();
  const [destroy, deleting] = useChatsFilesDestroyMutation();
  const input = useRef<HTMLInputElement>(null);
  const directoryInput = useRef<HTMLInputElement>(null);
  const batchInProgress = useRef(false);
  const [progress, setProgress] = useState<{
    completed: number;
    total: number;
  } | null>(null);
  const hintId = useId();
  const uploadDisabled =
    progress !== null ||
    uploading.isLoading ||
    (query.data?.pages[0]?.count ?? 0) >= 64;

  async function handleFilesChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    if (!files.length || batchInProgress.current) return;
    setError("");
    uploading.reset();
    const remaining = Math.max(0, 64 - (query.data?.pages[0]?.count ?? 0));
    if (files.length > remaining) {
      setError(
        `В чате может быть не более 64 файлов. Можно добавить ещё: ${remaining}. Выбрано: ${files.length}.`,
      );
      return;
    }
    for (const file of files) {
      if (file.size > 10 * 1024 * 1024) {
        setError(`«${file.name}»: файл не должен превышать 10 МиБ.`);
        return;
      }
      if (file.name.length > 200) {
        setError(
          `«${file.name}»: имя файла должно содержать не более 200 символов.`,
        );
        return;
      }
    }

    batchInProgress.current = true;
    setProgress({ completed: 0, total: files.length });
    const failures: string[] = [];
    try {
      for (const [index, file] of files.entries()) {
        try {
          await upload({ chatId, chatFileRequest: { file } }).unwrap();
        } catch (cause) {
          failures.push(`«${file.name}»: ${chatError(cause)}`);
          setError(failures.join(" "));
        }
        setProgress({ completed: index + 1, total: files.length });
      }
    } finally {
      batchInProgress.current = false;
      setProgress(null);
    }
  }

  return (
    <aside
      aria-label="Файлы обсуждения"
      data-chat-files-id={chatId}
      className="flex min-h-0 shrink-0 flex-col gap-5 px-5 pt-7 pb-6 xl:w-80 xl:overflow-y-auto"
    >
      <h2 className="text-h6">Файлы чата</h2>
      <Button
        variant="secondary"
        icon={<CloudArrowDownIcon />}
        iconPosition="right"
        disabled={uploadDisabled}
        aria-describedby={hintId}
        onClick={() => input.current?.click()}
      >
        {progress ? "Загрузка…" : "Загрузить файлы"}
      </Button>
      <Button
        variant="secondary"
        icon={<FolderIcon />}
        iconPosition="right"
        disabled={uploadDisabled}
        aria-describedby={hintId}
        onClick={() => directoryInput.current?.click()}
      >
        Загрузить папку
      </Button>
      <input
        ref={input}
        type="file"
        multiple
        aria-label="Выбрать файлы для чата"
        className="hidden"
        onChange={handleFilesChange}
      />
      <input
        ref={directoryInput}
        type="file"
        multiple
        {...{ webkitdirectory: "" }}
        aria-label="Выбрать папку с файлами для чата"
        className="hidden"
        onChange={handleFilesChange}
      />
      <span id={hintId} className="sr-only">
        До 10 МиБ на файл, не более 64 файлов. Файлы из папки и вложенных папок
        добавляются в общий список чата.
      </span>
      {progress && (
        <output className="text-sm text-content-500" aria-live="polite">
          Обработано файлов: {progress.completed} из {progress.total}
        </output>
      )}
      <p className="text-[11px] leading-4 font-semibold text-content-500">
        В ЭТОМ ОБСУЖДЕНИИ
      </p>
      <ChatFeedback error={error || uploading.error || deleting.error} />
      <ChatFeedback
        loading={query.isLoading}
        error={query.error}
        retry={() => query.refetch()}
      />
      <div className="flex flex-col gap-3">
        {query.currentData?.pages
          .flatMap((page) => page.results)
          .map((file) => (
            <ChatFileItem
              key={file.id}
              file={file}
              deleting={running || deleting.isLoading}
              onPreview={() => onPreview({ chatId, fileId: file.id })}
              onDelete={async () => {
                try {
                  await destroy({ chatId, id: file.id }).unwrap();
                } catch {
                  /* Shown above. */
                }
              }}
            />
          ))}
      </div>
      {!query.error && query.currentData?.pages[0]?.count === 0 && (
        <p className="text-label-md text-content-500">
          В этом чате пока нет файлов.
        </p>
      )}
      <ChatLoadMore
        hasNext={query.hasNextPage}
        busy={query.isFetching}
        onLoad={() => void query.fetchNextPage()}
      />
      <p className="text-[12px] leading-[17px] text-content-500">
        Файлы доступны только в этом чате
      </p>
      {running && (
        <p className="text-label-md text-content-500">
          Новые файлы попадут в контекст следующего сообщения.
        </p>
      )}
    </aside>
  );
}
