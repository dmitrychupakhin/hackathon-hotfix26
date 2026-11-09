"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import type { ChatCitation } from "@/shared/api/chats/document-preview-api";
import { Button } from "@/shared/ui/button";
import { citationPage } from "../model/citations";
import { highlightDocument } from "./highlight-document";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();
const options = { enableXfa: false, maxImageSize: 16_000_000 };

function PdfPage({
  number,
  width,
  citation,
  onUnavailable,
}: {
  number: number;
  width: number;
  citation?: ChatCitation;
  onUnavailable?: () => void;
}) {
  const host = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  const [ratio, setRatio] = useState(842 / 595);
  const focused = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!host.current) return;
    // Keep every page in the scrollable document, while bounding live canvases.
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { rootMargin: "800px 0px" },
    );
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  return (
    <section
      ref={host}
      data-pdf-page={number}
      aria-label={`Страница ${number}`}
      className="mb-5 scroll-mt-4"
    >
      <p className="mb-2 text-label-md text-content-500">Страница {number}</p>
      <div
        style={{ minHeight: Math.ceil(width * ratio) }}
        className="bg-content-0"
      >
        {(visible || !!citation) && (
          <Page
            pageNumber={number}
            width={width}
            renderAnnotationLayer={false}
            loading="Подготовка страницы…"
            error="Не удалось отобразить страницу."
            onLoadSuccess={(page) => {
              const viewport = page.getViewport({ scale: 1 });
              setRatio(viewport.height / viewport.width);
            }}
            onRenderTextLayerSuccess={() => {
              const layer = host.current?.querySelector<HTMLElement>(
                ".react-pdf__Page__textContent",
              );
              if (citation && layer) {
                const matched = highlightDocument(layer, citation.quote, {
                  scroll: focused.current !== citation.id,
                  align: "start",
                });
                if (matched) focused.current = citation.id;
                else onUnavailable?.();
              }
            }}
          />
        )}
      </div>
    </section>
  );
}

export default function DocumentPdf({
  url,
  citation,
  onUnavailable,
}: {
  url: string;
  citation?: ChatCitation;
  onUnavailable?: () => void;
}) {
  const host = useRef<HTMLElement>(null);
  const [pages, setPages] = useState(0);
  const [width, setWidth] = useState(480);
  const target = citationPage(citation);
  const pageNumbers = Array.from({ length: pages }, (_, index) => index + 1);
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(200, Math.floor(entry.contentRect.width))),
    );
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  return (
    <section ref={host} className="min-w-0" aria-label="Полный PDF-документ">
      <div className="mb-3 flex items-center justify-between gap-2 text-body-sm">
        <span>{pages ? `Всего страниц: ${pages}` : "Загрузка страниц…"}</span>
        {citation && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => {
              host.current
                ?.querySelector(`[data-pdf-page="${target}"]`)
                ?.scrollIntoView({ block: "start", behavior: "smooth" });
            }}
          >
            К цитате
          </Button>
        )}
      </div>
      <Document
        file={url}
        options={options}
        loading="Загрузка PDF…"
        error="Не удалось отобразить PDF."
        onLoadError={() => onUnavailable?.()}
        onLoadSuccess={({ numPages }) => setPages(numPages)}
      >
        {pageNumbers.map((number) => (
          <PdfPage
            key={`page-${number}`}
            number={number}
            width={width}
            citation={citation && number === target ? citation : undefined}
            onUnavailable={onUnavailable}
          />
        ))}
      </Document>
    </section>
  );
}
