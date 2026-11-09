"use client";

import DOMPurify from "dompurify";
import { useEffect, useRef, useState } from "react";
import type { ChatCitation } from "@/shared/api/chats/document-preview-api";
import { highlightDocument } from "./highlight-document";

export default function DocumentDocx({
  url,
  citation,
  onUnavailable,
}: {
  url: string;
  citation?: ChatCitation;
  onUnavailable?: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("Подготовка DOCX…");
  useEffect(() => {
    const controller = new AbortController();
    const worker = new Worker(
      new URL("./docx-parser.worker.ts", import.meta.url),
      { type: "module" },
    );
    let disposed = false;
    const timeout = setTimeout(() => {
      worker.terminate();
      if (!disposed) setStatus("Не удалось подготовить DOCX за 20 секунд.");
      if (!disposed) onUnavailable?.();
    }, 20000);
    worker.onmessage = ({
      data,
    }: MessageEvent<{ html?: string; error?: string }>) => {
      clearTimeout(timeout);
      worker.terminate();
      if (disposed) return;
      if (typeof data.html !== "string" || !host.current) {
        setStatus(data.error ?? "Ошибка предпросмотра DOCX.");
        onUnavailable?.();
        return;
      }
      // No links, styles, scripts, embedded content or external images from untrusted documents.
      host.current.innerHTML = DOMPurify.sanitize(data.html, {
        ALLOWED_TAGS: [
          "p",
          "br",
          "strong",
          "em",
          "b",
          "i",
          "u",
          "s",
          "h1",
          "h2",
          "h3",
          "h4",
          "h5",
          "h6",
          "table",
          "thead",
          "tbody",
          "tr",
          "td",
          "th",
          "ul",
          "ol",
          "li",
          "blockquote",
          "sup",
          "sub",
        ],
        ALLOWED_ATTR: ["colspan", "rowspan"],
      });
      const matched =
        citation && highlightDocument(host.current, citation.quote);
      setStatus(
        citation && !matched
          ? "Не удалось однозначно выделить цитату в представлении DOCX."
          : "",
      );
      if (citation && !matched) onUnavailable?.();
    };
    worker.onerror = () => {
      clearTimeout(timeout);
      worker.terminate();
      if (!disposed) setStatus("Не удалось отобразить DOCX.");
      if (!disposed) onUnavailable?.();
    };
    void fetch(url, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.arrayBuffer();
      })
      .then((data) => {
        if (!disposed) worker.postMessage(data, [data]);
      })
      .catch(() => {
        if (!disposed) {
          clearTimeout(timeout);
          worker.terminate();
          setStatus("Не удалось прочитать DOCX.");
          onUnavailable?.();
        }
      });
    return () => {
      disposed = true;
      controller.abort();
      clearTimeout(timeout);
      worker.terminate();
    };
  }, [url, citation, onUnavailable]);
  return (
    <div>
      <p className="mb-3 text-label-md text-content-500">
        Предпросмотр DOCX: заголовки, текст и таблицы. Расположение страниц
        может отличаться от Word.
      </p>
      {status && (
        <output className="mb-2 block text-body-sm text-content-500">
          {status}
        </output>
      )}
      <div
        ref={host}
        className="break-words bg-content-0 p-4 text-body-sm [&_h1]:text-h6 [&_h2]:text-body-lg [&_li]:ml-5 [&_ol]:list-decimal [&_p]:mb-3 [&_table]:w-full [&_td]:border [&_td]:p-2 [&_th]:border [&_th]:p-2 [&_ul]:list-disc"
      />
    </div>
  );
}
