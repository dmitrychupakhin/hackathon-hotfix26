import assert from "node:assert/strict";
import { afterEach, beforeEach, mock, test } from "node:test";
import { setImmediate } from "node:timers/promises";
import { makeStore } from "../../../src/_app/store/store";
import { chatsApi } from "../../../src/shared/api/chats/chats-api";
import { paginatedChatsApi } from "../../../src/shared/api/chats/paginated-api";
import { runStreamApi } from "../../../src/shared/api/chats/run-stream-api";

const NativeRequest = globalThis.Request;
const nativeFetch = globalThis.fetch;
const nativeWebSocket = globalThis.WebSocket;
const wsOrigin = process.env.NEXT_PUBLIC_AI_WS_ORIGIN;
let store: ReturnType<typeof makeStore>;
let requests: Request[];
let status = "running";
let mutationStatus = 200;
let pendingTickets = 0;
let journal: {
  seq: number;
  run_id: string;
  type: string;
  data: Record<string, unknown>;
}[];
let eventsAvailable = true;
class Socket {
  static instances: Socket[] = [];
  onopen?: () => void;
  onclose?: () => void;
  onerror?: () => void;
  onmessage?: (event: { data: string }) => void;
  closed = false;
  constructor(public url: URL) {
    Socket.instances.push(this);
  }
  close() {
    if (!this.closed) {
      this.closed = true;
      this.onclose?.();
    }
  }
  emit(seq: number, type: string, data: Record<string, unknown>) {
    this.onmessage?.({
      data: JSON.stringify({ seq, run_id: "ai-id", type, data }),
    });
  }
}
const runArgs = { chatId: "chat-id", id: "django-run" };
const watchArgs = { chatId: "chat-id", runId: "django-run" };
async function settle() {
  for (let i = 0; i < 8; i++) await setImmediate();
}
beforeEach(() => {
  requests = [];
  status = "running";
  mutationStatus = 200;
  pendingTickets = 0;
  journal = [];
  eventsAvailable = true;
  Socket.instances = [];
  process.env.NEXT_PUBLIC_AI_WS_ORIGIN = "https://example.test";
  globalThis.Request = class extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(
        typeof input === "string" ? new URL(input, "http://localhost") : input,
        init,
      );
    }
  };
  globalThis.WebSocket = Socket as unknown as typeof WebSocket;
  globalThis.fetch = async (input) => {
    const request = input as Request;
    requests.push(request);
    const url = new URL(request.url);
    if (url.pathname.endsWith("/events")) {
      if (!eventsAvailable)
        return Response.json({ detail: ["Unavailable"] }, { status: 502 });
      const after = Number(url.searchParams.get("after") || 0);
      return Response.json(
        journal.filter((event) => event.seq > after).slice(0, 100),
      );
    }
    if (url.pathname.endsWith("ws-ticket")) {
      if (pendingTickets-- > 0)
        return Response.json({ detail: ["Pending"] }, { status: 409 });
      return Response.json({
        ticket: "ticket",
        path: "/ai/api/v1/runs/ai-id/ws",
        expires_at: 9999999999,
      });
    }
    if (url.pathname.includes("/runs/"))
      return Response.json({
        id: "django-run",
        status,
        error: "",
        created_at: "now",
        updated_at: "now",
      });
    if (request.method !== "GET")
      return mutationStatus >= 400
        ? Response.json({ detail: ["Failed"] }, { status: mutationStatus })
        : Response.json({ id: "new-id" });
    return Response.json({
      count: 31,
      next: url.searchParams.get("page") === "2" ? null : "?page=2",
      results: [{ id: url.searchParams.get("page") || "1" }],
    });
  };
  store = makeStore();
});
afterEach(async () => {
  store.dispatch(chatsApi.util.resetApiState());
  await settle();
  mock.timers.reset();
  globalThis.Request = NativeRequest;
  globalThis.fetch = nativeFetch;
  globalThis.WebSocket = nativeWebSocket;
  if (wsOrigin === undefined) delete process.env.NEXT_PUBLIC_AI_WS_ORIGIN;
  else process.env.NEXT_PUBLIC_AI_WS_ORIGIN = wsOrigin;
});
test("file upload sends multipart bytes with filename and session credentials", async () => {
  const file = new File(["document"], "brief.pdf", { type: "application/pdf" });
  await store
    .dispatch(
      chatsApi.endpoints.chatsFilesCreate.initiate({
        chatId: "chat-id",
        chatFileRequest: { file },
      }),
    )
    .unwrap();
  const request = requests[0];
  assert.equal(request.credentials, "include");
  assert.match(
    request.headers.get("content-type") || "",
    /^multipart\/form-data; boundary=/,
  );
  const uploaded = (await request.formData()).get("file");
  assert.ok(uploaded instanceof File);
  assert.equal(uploaded.name, "brief.pdf");
  assert.equal(await uploaded.text(), "document");
});
test("failed file mutation preserves cached file list", async () => {
  await store
    .dispatch(chatsApi.endpoints.chatsFilesList.initiate({ chatId: "chat-id" }))
    .unwrap();
  mutationStatus = 409;
  await assert.rejects(
    store
      .dispatch(
        chatsApi.endpoints.chatsFilesDestroy.initiate({
          chatId: "chat-id",
          id: "file-id",
        }),
      )
      .unwrap(),
  );
  await settle();
  assert.equal(requests.filter((r) => r.method === "GET").length, 1);
});
test("infinite history retains pages in RTK Query and delegates to generated HTTP", async () => {
  await store
    .dispatch(paginatedChatsApi.endpoints.chatHistory.initiate())
    .unwrap();
  await store
    .dispatch(
      paginatedChatsApi.endpoints.chatHistory.initiate(undefined, {
        direction: "forward",
      }),
    )
    .unwrap();
  const data = paginatedChatsApi.endpoints.chatHistory.select()(
    store.getState(),
  ).data;
  assert.deepEqual(data?.pageParams, [1, 2]);
  assert.equal(data?.pages.length, 2);
  assert.ok(requests.every((r) => new URL(r.url).pathname === "/api/chats"));
});
test("identical stream subscriptions share one socket and last unsubscribe closes it", async () => {
  const first = store.dispatch(
    runStreamApi.endpoints.watchChatRun.initiate(watchArgs),
  );
  const second = store.dispatch(
    runStreamApi.endpoints.watchChatRun.initiate(watchArgs),
  );
  await settle();
  assert.equal(Socket.instances.length, 1);
  first.unsubscribe();
  await settle();
  assert.equal(Socket.instances[0].closed, false);
  second.unsubscribe();
  await new Promise((resolve) => setTimeout(resolve, 10));
  await settle();
  assert.equal(Socket.instances[0].closed, true);
});
test("pending ticket is retried; replay uses last seq and a fresh ticket", async () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  pendingTickets = 1;
  store.dispatch(runStreamApi.endpoints.watchChatRun.initiate(watchArgs));
  await settle();
  assert.equal(Socket.instances.length, 0);
  mock.timers.tick(2000);
  await settle();
  assert.equal(Socket.instances.length, 1);
  const first = Socket.instances[0];
  first.onopen?.();
  first.emit(5, "harness.step", {
    step_id: "x",
    title: "Проверка",
    message: "Проверка",
    status: "started",
  });
  first.close();
  mock.timers.tick(2000);
  await settle();
  assert.equal(Socket.instances.length, 2);
  assert.equal(Socket.instances[1].url.searchParams.get("after"), "5");
  assert.equal(requests.filter((r) => r.url.endsWith("/ws-ticket")).length, 3);
});
test("AI completion waits for Django persistence before refreshing history", async () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  store.dispatch(
    chatsApi.endpoints.chatsMessagesList.initiate({ chatId: "chat-id" }),
  );
  store.dispatch(runStreamApi.endpoints.watchChatRun.initiate(watchArgs));
  await settle();
  const socket = Socket.instances[0];
  socket.emit(1, "harness.step", {
    step_id: "prepare",
    title: "Подготовка",
    message: "Подготовка",
    status: "started",
  });
  socket.emit(2, "harness.step", {
    step_id: "prepare",
    title: "Подготовка",
    message: "Подготовка",
    status: "completed",
  });
  socket.emit(3, "answer.completed", { answer: { answer: "Готово" } });
  socket.emit(4, "run.completed", {});
  assert.equal(socket.closed, true);
  mock.timers.tick(2000);
  await settle();
  assert.equal(requests.filter((r) => r.url.includes("/messages")).length, 1);
  status = "completed";
  mock.timers.tick(2000);
  await settle();
  assert.equal(requests.filter((r) => r.url.includes("/messages")).length, 2);
  assert.equal(
    runStreamApi.endpoints.watchChatRun.select(watchArgs)(store.getState()).data
      ?.connection,
    "closed",
  );
  assert.equal(
    chatsApi.endpoints.chatsRunsRetrieve.select(runArgs)(store.getState()).data
      ?.status,
    "completed",
  );
  assert.deepEqual(
    runStreamApi.endpoints.watchChatRun.select(watchArgs)(store.getState()).data
      ?.steps,
    [
      {
        step_id: "prepare",
        title: "Подготовка",
        message: "Подготовка",
        status: "completed",
        updated_seq: 2,
      },
    ],
  );
});

test("switching the visible chat retains the page-owned background stream", async () => {
  const owner = store.dispatch(
    runStreamApi.endpoints.watchChatRun.initiate(watchArgs),
  );
  const visible = store.dispatch(
    runStreamApi.endpoints.watchChatRun.initiate(watchArgs),
  );
  await settle();
  visible.unsubscribe();
  await settle();
  const socket = Socket.instances[0];
  socket.emit(1, "harness.step", {
    step_id: "prepare",
    title: "Подготовка",
    message: "Подготовка",
    status: "completed",
  });
  assert.equal(socket.closed, false);
  const returned = store.dispatch(
    runStreamApi.endpoints.watchChatRun.initiate(watchArgs),
  );
  assert.equal((await returned.unwrap()).steps[0].status, "completed");
  assert.equal(Socket.instances.length, 1);
  owner.unsubscribe();
  returned.unsubscribe();
});

test("five failed tickets stop automatic reconnect; manual attempt starts a new lifecycle", async () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  let ticketRequests = 0;
  eventsAvailable = false;
  const fetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    if ((input as Request).url.endsWith("/ws-ticket")) {
      ticketRequests++;
      return Response.json({ detail: ["Unavailable"] }, { status: 502 });
    }
    return fetch(input, init);
  };
  store.dispatch(runStreamApi.endpoints.watchChatRun.initiate(watchArgs));
  await settle();
  for (const ms of [1000, 2000, 4000, 8000]) {
    mock.timers.tick(ms);
    await settle();
  }
  assert.equal(ticketRequests, 5);
  assert.equal(
    runStreamApi.endpoints.watchChatRun.select(watchArgs)(store.getState()).data
      ?.connection,
    "error",
  );
  mock.timers.tick(15000);
  await settle();
  assert.equal(ticketRequests, 5);
  globalThis.fetch = fetch;
  store.dispatch(
    runStreamApi.endpoints.watchChatRun.initiate({ ...watchArgs, attempt: 1 }),
  );
  await settle();
  assert.equal(Socket.instances.length, 1);
});

test("HTTP replay supplies real progress when WebSocket fails and merges later frames", async () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const entry = (seq: number, type: string, data: Record<string, unknown>) => ({
    seq,
    run_id: "ai-id",
    type,
    data,
  });
  journal.push(
    entry(1, "harness.step", {
      step_id: "prepare",
      kind: "prepare",
      title: "Подготовка",
      message: "Подготовка",
      status: "completed",
    }),
  );
  store.dispatch(runStreamApi.endpoints.watchChatRun.initiate(watchArgs));
  await settle();
  assert.equal(Socket.instances[0].url.searchParams.get("after"), "1");
  Socket.instances[0].close();
  journal.push(
    entry(2, "harness.step", {
      step_id: "answer",
      kind: "answer",
      title: "Ответ",
      message: "Ответ",
      status: "started",
    }),
  );
  mock.timers.tick(2000);
  await settle();
  const snapshot = () =>
    runStreamApi.endpoints.watchChatRun.select(watchArgs)(store.getState())
      .data;
  assert.equal(snapshot()?.steps.length, 2);
  const socket = Socket.instances.at(-1)!;
  assert.equal(socket.url.searchParams.get("after"), "2");
  socket.emit(2, "harness.step", journal[1].data);
  socket.emit(3, "harness.step", { ...journal[1].data, status: "completed" });
  assert.equal(snapshot()?.steps.length, 2);
  assert.equal(snapshot()?.steps[1].status, "completed");
});

test("a terminal run reload replays all event pages before closing observation", async () => {
  status = "completed";
  journal = Array.from({ length: 105 }, (_, index) => ({
    seq: index + 1,
    run_id: "ai-id",
    type: "harness.step",
    data: {
      step_id: `tool-${index}`,
      kind: "tool",
      title: "Чтение",
      message: "Чтение",
      status: "completed",
    },
  }));
  journal.push({ seq: 106, run_id: "ai-id", type: "run.completed", data: {} });
  store.dispatch(runStreamApi.endpoints.watchChatRun.initiate(watchArgs));
  await settle();
  const stream = runStreamApi.endpoints.watchChatRun.select(watchArgs)(
    store.getState(),
  ).data;
  assert.equal(stream?.seq, 106);
  assert.equal(stream?.steps.length, 105);
  assert.equal(stream?.terminal, true);
  assert.equal(stream?.connection, "closed");
  assert.equal(Socket.instances.length, 0);
  assert.equal(
    requests.filter((request) =>
      new URL(request.url).pathname.endsWith("/events"),
    ).length,
    2,
  );
});

test("cancelled Django run closes observation and reset closes all sockets", async () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  store.dispatch(runStreamApi.endpoints.watchChatRun.initiate(watchArgs));
  await settle();
  status = "cancelled";
  await store
    .dispatch(chatsApi.endpoints.chatsRunsCancelCreate.initiate(runArgs))
    .unwrap();
  mock.timers.tick(2000);
  await settle();
  assert.equal(Socket.instances[0].closed, true);
  assert.equal(
    runStreamApi.endpoints.watchChatRun.select(watchArgs)(store.getState()).data
      ?.terminal,
    true,
  );
  status = "running";
  store.dispatch(
    runStreamApi.endpoints.watchChatRun.initiate({
      ...watchArgs,
      runId: "second-run",
    }),
  );
  await settle();
  store.dispatch(chatsApi.util.resetApiState());
  await settle();
  assert.ok(Socket.instances.every((s) => s.closed));
});

test("invalidating accumulated history and messages retains successful refetch results", async () => {
  await store
    .dispatch(paginatedChatsApi.endpoints.chatHistory.initiate())
    .unwrap();
  await store
    .dispatch(paginatedChatsApi.endpoints.chatMessages.initiate("chat-id"))
    .unwrap();
  await store
    .dispatch(
      chatsApi.endpoints.chatsMessagesCreate.initiate({
        chatId: "chat-id",
        chatMessageRequest: { content: "New message" },
      }),
    )
    .unwrap();
  await settle();
  const history = paginatedChatsApi.endpoints.chatHistory.select()(
    store.getState(),
  );
  const messages = paginatedChatsApi.endpoints.chatMessages.select("chat-id")(
    store.getState(),
  );
  assert.equal(history.status, "fulfilled");
  assert.equal(messages.status, "fulfilled");
  assert.equal(history.error, undefined);
  assert.equal(messages.error, undefined);
});
