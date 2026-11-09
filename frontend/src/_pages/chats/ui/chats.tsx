"use client";

import { skipToken } from "@reduxjs/toolkit/query";
import { Fragment, useEffect, useState } from "react";
import { shallowEqual, useSelector } from "react-redux";
import type { RootState } from "@/_app/store/store";
import {
  chatsApi,
  useChatsRetrieveQuery,
  useChatsRunsRetrieveQuery,
  useWatchChatRunQuery,
} from "@/shared/api/chats";
import type { PreviewSelection } from "@/shared/api/chats/document-preview-api";
import { isActiveRun } from "../model/chat-utils";
import { parsePreviewLink, previewLink } from "../model/citations";
import { ChatConversation } from "./chat-conversation";
import { ChatDocumentPreview } from "./chat-document-preview";
import { ChatFiles } from "./chat-files";
import { ChatHistory } from "./chat-history";

type ObservedRun = {
  chatId: string;
  runId: string;
  messageId?: string;
  attempt: number;
};
function RunObserver({ run }: { run: ObservedRun }) {
  useWatchChatRunQuery({
    chatId: run.chatId,
    runId: run.runId,
    attempt: run.attempt,
  });
  useChatsRunsRetrieveQuery({ chatId: run.chatId, id: run.runId });
  return null;
}
export function Chats() {
  const [selected, setSelected] = useState<string>();
  const [runs, setRuns] = useState<ObservedRun[]>([]);
  const [preview, setPreview] = useState<PreviewSelection>();
  const chat = useChatsRetrieveQuery(selected ? { id: selected } : skipToken);
  useEffect(() => {
    const restoreLink = () => {
      const target = parsePreviewLink(window.location.hash);
      if (target) {
        setSelected(target.chatId);
        setPreview(target);
      } else {
        setPreview(undefined);
      }
    };
    restoreLink();
    window.addEventListener("hashchange", restoreLink);
    return () => window.removeEventListener("hashchange", restoreLink);
  }, []);
  useEffect(() => {
    const latest = (
      chat.currentData as { latest_run?: { id: string } | null } | undefined
    )?.latest_run;
    if (selected && latest?.id)
      setRuns((current) =>
        current.some((run) => run.chatId === selected)
          ? current
          : [...current, { chatId: selected, runId: latest.id, attempt: 0 }],
      );
  }, [selected, chat.currentData]);
  const openPreview = (target: PreviewSelection) => {
    setPreview(target);
    window.history.replaceState(
      null,
      "",
      previewLink(target, window.location.href),
    );
  };
  const currentRun = runs.find((run) => run.chatId === selected);
  const status = useChatsRunsRetrieveQuery(
    currentRun
      ? { chatId: currentRun.chatId, id: currentRun.runId }
      : skipToken,
  );
  const stream = useWatchChatRunQuery(
    currentRun
      ? {
          chatId: currentRun.chatId,
          runId: currentRun.runId,
          attempt: currentRun.attempt,
        }
      : skipToken,
  );
  const running = useSelector(
    (state: RootState) =>
      runs
        .filter((run) => {
          const data = chatsApi.endpoints.chatsRunsRetrieve.select({
            chatId: run.chatId,
            id: run.runId,
          })(state).data;
          return !data || isActiveRun(data.status);
        })
        .map((run) => run.chatId),
    shallowEqual,
  );
  const active = !!selected && running.includes(selected);
  return (
    <div className="flex min-h-[calc(100dvh-88px)] flex-col text-content-900 xl:h-[calc(100dvh-88px)] xl:min-h-0 xl:flex-row xl:overflow-hidden">
      {runs.map((run) => (
        <RunObserver key={`${run.runId}-${run.attempt}`} run={run} />
      ))}
      <div
        className={
          preview && preview.chatId === selected
            ? "hidden min-[1800px]:contents"
            : "contents"
        }
      >
        <ChatHistory
          selected={selected}
          onSelect={(id) => {
            setSelected(id);
            setPreview(undefined);
            window.history.replaceState(
              null,
              "",
              `${window.location.pathname}${window.location.search}`,
            );
          }}
          running={running}
          onDelete={(id) => {
            setRuns((current) => current.filter((run) => run.chatId !== id));
            if (selected === id) setSelected(undefined);
          }}
        />
      </div>
      {selected ? (
        <Fragment key={selected}>
          <ChatConversation
            chatId={selected}
            running={active}
            runId={currentRun?.runId}
            messageId={currentRun?.messageId}
            stream={
              stream.currentData
                ? {
                    ...stream.currentData,
                    error:
                      status.currentData?.error || stream.currentData.error,
                  }
                : undefined
            }
            onPreview={openPreview}
            onRetry={() =>
              setRuns((current) =>
                current.map((run) =>
                  run.chatId === selected
                    ? { ...run, attempt: run.attempt + 1 }
                    : run,
                ),
              )
            }
            onRun={(runId, messageId) =>
              setRuns((current) => [
                ...current.filter((run) => run.chatId !== selected),
                { chatId: selected, runId, messageId, attempt: 0 },
              ])
            }
          />
          {preview?.chatId === selected ? (
            <ChatDocumentPreview
              key={`${selected}-${preview.fileId}-${preview.citation?.id ?? "file"}`}
              selection={preview}
              onClose={() => {
                setPreview(undefined);
                window.history.replaceState(
                  null,
                  "",
                  `${window.location.pathname}${window.location.search}`,
                );
              }}
            />
          ) : (
            <ChatFiles
              chatId={selected}
              running={active}
              onPreview={openPreview}
            />
          )}
        </Fragment>
      ) : (
        <section
          aria-label="Выбор обсуждения"
          className="flex min-h-96 flex-1 items-center justify-center border-content-100 p-8 text-content-500 xl:border-x"
        >
          <p>Выберите обсуждение или создайте новый чат.</p>
        </section>
      )}
    </div>
  );
}
