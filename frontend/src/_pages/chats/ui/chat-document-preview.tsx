"use client";

import { skipToken } from "@reduxjs/toolkit/query";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  type PreviewSelection,
  useChatDocumentContentQuery,
  useChatDocumentPreviewQuery,
} from "@/shared/api/chats/document-preview-api";
import { Button } from "@/shared/ui/button";
import { citationRange } from "../model/citations";
import { documentWarning } from "../model/document-warnings";
import { ChatFeedback } from "./chat-feedback";

const DocumentPdf = dynamic(() => import("./document-pdf"), {
  ssr: false,
  loading: () => <p>Подготовка PDF…</p>,
});
const DocumentDocx = dynamic(() => import("./document-docx"), {
  ssr: false,
  loading: () => <p>Подготовка DOCX…</p>,
});

function CanonicalText({
  text,
  range,
}: {
  text: string;
  range?: { start: number; end: number };
}) {
  const mark = useRef<HTMLElement>(null);
  useEffect(() => {
    if (range)
      mark.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [range]);
  return (
    <pre className="font-sans text-body-sm whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
      {range ? (
        <>
          {text.slice(0, range.start)}
          <mark
            ref={mark}
            className="rounded bg-accent-200 px-0.5 text-content-900 outline-1 outline-accent-500"
          >
            {text.slice(range.start, range.end)}
          </mark>
          {text.slice(range.end)}
        </>
      ) : (
        text
      )}
    </pre>
  );
}

export function ChatDocumentPreview({
  selection,
  onClose,
}: {
  selection: PreviewSelection;
  onClose: () => void;
}) {
  const query = useChatDocumentPreviewQuery(selection);
  const preview = query.currentData;
  const binary = useChatDocumentContentQuery(
    preview && (preview.format === "pdf" || preview.format === "docx")
      ? {
          chatId: selection.chatId,
          fileId: selection.fileId,
          textSha256: preview.text_sha256,
          version: preview.version,
        }
      : skipToken,
    { refetchOnFocus: false, refetchOnReconnect: false },
  );
  const [textView, setTextView] = useState(false);
  const [originalUnavailable, setOriginalUnavailable] = useState(false);
  const onOriginalUnavailable = useCallback(
    () => setOriginalUnavailable(true),
    [],
  );
  const range = preview && citationRange(preview, selection.citation);
  const stale =
    query.error && "status" in query.error && query.error.status === 409;
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  return (
    <aside
      aria-label="Предпросмотр документа"
      className="fixed inset-y-0 right-0 z-50 flex h-dvh w-[min(90vw,700px)] min-h-0 min-w-0 flex-col overflow-hidden border-l border-content-100 bg-content-0 shadow-2xl xl:static xl:z-auto xl:h-auto xl:w-[min(43vw,700px)] xl:shrink-0 xl:shadow-none"
    >
      <div className="flex shrink-0 items-start justify-between gap-3 border-b border-content-100 bg-content-0 px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-h6">Документ</h2>
          <p className="break-words text-body-sm text-content-500">
            {preview?.name ?? selection.citation?.file_name}
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={onClose}
          aria-label="Закрыть предпросмотр"
        >
          Закрыть
        </Button>
      </div>
      <div
        data-document-scroll
        className="min-h-0 flex-1 overflow-y-auto px-5 py-4 [&>*+*]:mt-4"
      >
        {stale ? (
          <p role="alert" className="text-body-sm">
            Документ изменился после ответа. Цитата относится к другой версии.
            Откройте актуальный файл в списке файлов.
          </p>
        ) : (
          <ChatFeedback
            loading={query.isLoading}
            error={query.error}
            retry={() => query.refetch()}
          />
        )}
        {preview && (
          <>
            {selection.citation && !range && (
              <p role="alert" className="text-body-sm">
                Не удалось подтвердить положение цитаты в этой версии. Выделение
                не показано.
              </p>
            )}
            {preview.partial && (
              <output className="text-body-sm text-content-500">
                Текст извлечён не полностью. Ответ мог учитывать не весь
                документ.
              </output>
            )}
            {[
              ...new Set(preview.warnings.map(documentWarning).filter(Boolean)),
            ].map((warning, index) => (
              <p
                key={`${index}-${warning}`}
                className="text-label-md text-content-500"
              >
                {warning}
              </p>
            ))}
            {!textView &&
              (preview.format === "pdf" || preview.format === "docx") && (
                <>
                  <ChatFeedback
                    loading={binary.isLoading}
                    error={binary.error}
                    retry={() => binary.refetch()}
                  />
                  {binary.currentData &&
                    (preview.format === "pdf" ? (
                      <DocumentPdf
                        url={binary.currentData}
                        citation={range ? selection.citation : undefined}
                        onUnavailable={onOriginalUnavailable}
                      />
                    ) : (
                      <DocumentDocx
                        url={binary.currentData}
                        citation={range ? selection.citation : undefined}
                        onUnavailable={onOriginalUnavailable}
                      />
                    ))}
                  {(originalUnavailable || binary.error) && (
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => setTextView(true)}
                    >
                      Показать полный текст документа
                    </Button>
                  )}
                </>
              )}
            {preview.format === "md" && (
              <p className="text-label-md text-content-500">
                Markdown показан как исходный текст для точного выделения
                цитаты.
              </p>
            )}
            {(textView ||
              preview.format === "txt" ||
              preview.format === "md") && (
              <CanonicalText text={preview.text} range={range} />
            )}
          </>
        )}
      </div>
    </aside>
  );
}
