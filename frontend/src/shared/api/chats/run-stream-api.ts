import type { skipToken } from "@reduxjs/toolkit/query";
import { chatsApi } from "./chats-api";
import {
  applyRunEvent,
  buildRunSocketUrl,
  parseRunEvent,
  type RunStream,
} from "./run-events";

export type WatchChatRunArg = {
  chatId: string;
  runId: string;
  attempt?: number;
};
const terminal = (status?: string) =>
  ["completed", "failed", "cancelled", "interrupted"].includes(status ?? "");
export const runStreamApi = chatsApi.injectEndpoints({
  endpoints: (build) => ({
    watchChatRun: build.query<RunStream, WatchChatRunArg>({
      queryFn: () => ({
        data: { connection: "connecting", seq: 0, steps: [], terminal: false },
      }),
      keepUnusedDataFor: 0,
      async onCacheEntryAdded(
        { chatId, runId },
        {
          cacheDataLoaded,
          cacheEntryRemoved,
          updateCachedData,
          dispatch,
          getCacheEntry,
        },
      ) {
        let disposed = false;
        let socket: WebSocket | undefined;
        let wake: (() => void) | undefined;
        const removed = cacheEntryRemoved.then(() => {
          disposed = true;
          socket?.close();
          wake?.();
        });
        const pause = (ms: number) =>
          new Promise<void>((resolve) => {
            const timer = setTimeout(() => {
              wake = undefined;
              resolve();
            }, ms);
            wake = () => {
              clearTimeout(timer);
              resolve();
            };
          });
        let failures = 0;
        let nextConnect = 0;
        let aiTerminal = false;
        let aiRunId: string | undefined;
        let pollingAvailable = false;
        let lastFrame = Date.now();
        const consume = (value: unknown) => {
          const id =
            aiRunId ||
            (typeof value === "object" &&
            value !== null &&
            "run_id" in value &&
            typeof value.run_id === "string"
              ? value.run_id
              : "");
          const event = parseRunEvent(value, id);
          if (!event) return false;
          aiRunId = event.run_id;
          updateCachedData((draft) => applyRunEvent(draft, event));
          if (getCacheEntry().data?.terminal) aiTerminal = true;
          return true;
        };
        const replay = async () => {
          // Same-origin authenticated replay also works when an upgrade proxy or
          // a network intermediary is unavailable. Both transports use one cursor.
          for (let page = 0; page < 100 && !disposed; page++) {
            const after = getCacheEntry().data?.seq ?? 0;
            const request = dispatch(
              chatsApi.endpoints.chatsRunsEventsList.initiate(
                { chatId, id: runId, after, limit: 100 },
                { forceRefetch: true, subscribe: false },
              ),
            );
            const result = await Promise.race([request, removed]);
            if (disposed) {
              request.abort();
              return false;
            }
            if (!Array.isArray(result?.data)) return false;
            for (const event of result.data) consume(event);
            if (
              result.data.length < 100 ||
              (getCacheEntry().data?.seq ?? 0) <= after
            )
              return true;
          }
          return false;
        };
        try {
          await cacheDataLoaded;
          while (!disposed) {
            const request = dispatch(
              chatsApi.endpoints.chatsRunsRetrieve.initiate(
                { chatId, id: runId },
                { forceRefetch: true, subscribe: false },
              ),
            );
            const result = await Promise.race([request, removed]);
            if (disposed) {
              request.abort();
              break;
            }
            const djangoTerminal =
              !!result?.data && terminal(result.data.status);
            if (!socket || djangoTerminal) {
              const replayed = await replay();
              pollingAvailable = replayed;
              if (disposed) break;
              if (replayed && !socket && !djangoTerminal)
                updateCachedData((draft) => {
                  draft.connection = "polling";
                  draft.error = undefined;
                });
            }
            if (result?.data && djangoTerminal) {
              const finalRun = result.data;
              aiTerminal = true;
              updateCachedData((draft) => {
                draft.terminal = true;
                draft.connection = "closed";
                draft.error = finalRun.error || undefined;
                for (const step of draft.steps)
                  if (step.status === "started")
                    step.status =
                      finalRun.status === "cancelled"
                        ? "cancelled"
                        : finalRun.status === "failed"
                          ? "failed"
                          : "interrupted";
              });
              dispatch(
                chatsApi.util.invalidateTags([
                  { type: "ChatMessages", id: chatId },
                  { type: "Chat", id: chatId },
                  { type: "Chat", id: "LIST" },
                ]),
              );
              break;
            }
            if (socket && Date.now() - lastFrame > 45000) socket.close();
            if (
              !aiTerminal &&
              !socket &&
              Date.now() >= nextConnect &&
              failures < 5
            ) {
              const ticketRequest = dispatch(
                chatsApi.endpoints.chatsRunsWsTicketCreate.initiate({
                  chatId,
                  id: runId,
                }),
              );
              const response = await Promise.race([ticketRequest, removed]);
              ticketRequest.reset();
              if (disposed) {
                ticketRequest.abort();
                break;
              }
              if (response?.data) {
                const ticket = response.data;
                let url: URL;
                try {
                  url = buildRunSocketUrl(
                    ticket.path,
                    ticket.ticket,
                    getCacheEntry().data?.seq ?? 0,
                    process.env.NEXT_PUBLIC_AI_WS_ORIGIN ||
                      window.location.origin,
                  );
                } catch {
                  // A deployment URL error must not stop authenticated HTTP replay.
                  failures = 5;
                  updateCachedData((draft) => {
                    draft.connection = pollingAvailable ? "polling" : "error";
                    if (!pollingAvailable)
                      draft.error = "Не удалось открыть события AI.";
                  });
                  await pause(2000);
                  continue;
                }
                aiRunId = url.pathname.split("/").at(-2) ?? aiRunId;
                const ws = new WebSocket(url);
                socket = ws;
                lastFrame = Date.now();
                ws.onopen = () => {
                  if (!disposed)
                    updateCachedData((d) => {
                      d.connection = "connected";
                      d.error = undefined;
                    });
                };
                ws.onmessage = ({ data }) => {
                  if (disposed || typeof data !== "string") return;
                  lastFrame = Date.now();
                  try {
                    if (consume(JSON.parse(data))) failures = 0;
                    if (aiTerminal) ws.close();
                  } catch {
                    /* Ignore malformed frames without losing the last valid cursor. */
                  }
                };
                ws.onclose = () => {
                  socket = undefined;
                  if (disposed || aiTerminal) return;
                  failures += 1;
                  nextConnect =
                    Date.now() + Math.min(1000 * 2 ** (failures - 1), 15000);
                  updateCachedData((draft) => {
                    draft.connection = pollingAvailable
                      ? "polling"
                      : failures >= 5
                        ? "error"
                        : "reconnecting";
                    if (failures >= 5 && !pollingAvailable)
                      draft.error =
                        "Не удалось восстановить соединение. Попробуйте подключиться снова.";
                  });
                };
                ws.onerror = () => ws.close();
              } else if (
                response?.error &&
                !("status" in response.error && response.error.status === 409)
              ) {
                failures += 1;
                nextConnect =
                  Date.now() + Math.min(1000 * 2 ** (failures - 1), 15000);
                updateCachedData((draft) => {
                  draft.connection = pollingAvailable
                    ? "polling"
                    : failures >= 5
                      ? "error"
                      : "reconnecting";
                  draft.error =
                    failures >= 5 && !pollingAvailable
                      ? "Не удалось подключиться к событиям AI. Попробуйте снова."
                      : undefined;
                });
              }
            }
            await pause(
              !socket && nextConnect > Date.now()
                ? Math.min(2000, nextConnect - Date.now())
                : 2000,
            );
          }
        } catch {
          if (!disposed)
            updateCachedData((draft) => {
              draft.connection = "error";
              draft.error = "Не удалось открыть события AI.";
            });
        } finally {
          aiTerminal = true;
          socket?.close();
          wake?.();
        }
      },
    }),
  }),
});
const { useWatchChatRunQuery: useRawWatchChatRunQuery } = runStreamApi;
export function useWatchChatRunQuery(arg: WatchChatRunArg | typeof skipToken) {
  // The lifecycle reconnects on its own; a focus refetch must not reset seq/steps.
  return useRawWatchChatRunQuery(arg, {
    refetchOnFocus: false,
    refetchOnReconnect: false,
  });
}
