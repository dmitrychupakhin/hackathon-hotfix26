import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { setImmediate } from "node:timers/promises";
import { makeStore } from "../../../src/_app/store/store";
import { comparisonsApi } from "../../../src/shared/api/comparisons";

const NativeRequest = globalThis.Request;
const nativeFetch = globalThis.fetch;
let store: ReturnType<typeof makeStore>;
let requests: Request[];
let mutationStatus: number;
let jobStatus: "running" | "completed";
const job = () => ({
  id: "job",
  model_id: "model",
  status: jobStatus,
  stage: jobStatus,
  result: null,
  error: "",
  created_at: "now",
  updated_at: "now",
});
beforeEach(() => {
  store = makeStore();
  requests = [];
  mutationStatus = 202;
  jobStatus = "running";
  globalThis.Request = class extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(
        typeof input === "string" ? new URL(input, "http://localhost") : input,
        init,
      );
    }
  };
  globalThis.fetch = async (input) => {
    const request = input as Request;
    requests.push(request);
    if (request.method === "POST")
      return Response.json(
        mutationStatus === 202 ? job() : { detail: ["Rejected"] },
        { status: mutationStatus },
      );
    if (new URL(request.url).pathname.endsWith("/job"))
      return Response.json(job());
    return Response.json({
      count: 1,
      next: null,
      previous: null,
      results: [job()],
    });
  };
});
afterEach(() => {
  store.dispatch(comparisonsApi.util.resetApiState());
  globalThis.Request = NativeRequest;
  globalThis.fetch = nativeFetch;
});
async function settle() {
  for (let i = 0; i < 10; i++) await setImmediate();
}
function create() {
  return store.dispatch(
    comparisonsApi.endpoints.comparisonsCreate.initiate({
      comparisonCreateRequest: {
        questions: new File(["q"], "questions.csv"),
        answers: new File(["a"], "answers.json"),
        documents: [
          new File(["one"], "one.pdf"),
          new File(["two"], "two.docx"),
        ],
        model_id: "model",
      },
    }),
  );
}
test("creation sends repeated document multipart fields with original filenames and session credentials", async () => {
  await create().unwrap();
  const request = requests[0];
  assert.equal(request.credentials, "include");
  assert.equal(new URL(request.url).pathname, "/api/comparisons");
  assert.match(
    request.headers.get("content-type") ?? "",
    /^multipart\/form-data; boundary=/,
  );
  const form = await request.formData();
  assert.equal((form.get("questions") as File).name, "questions.csv");
  assert.equal((form.get("answers") as File).name, "answers.json");
  assert.deepEqual(
    form.getAll("documents").map((file) => (file as File).name),
    ["one.pdf", "two.docx"],
  );
  assert.equal(form.get("model_id"), "model");
});
test("successful creation refreshes history; failed creation retains the list cache", async () => {
  await store
    .dispatch(
      comparisonsApi.endpoints.comparisonsList.initiate({
        page: 1,
        pageSize: 30,
      }),
    )
    .unwrap();
  await create().unwrap();
  await settle();
  assert.equal(requests.filter((r) => r.method === "GET").length, 2);
  mutationStatus = 400;
  await assert.rejects(create().unwrap());
  await settle();
  assert.equal(requests.filter((r) => r.method === "GET").length, 2);
});
test("terminal detail transition refreshes the list and exposes the saved terminal status", async () => {
  await store
    .dispatch(comparisonsApi.endpoints.comparisonsList.initiate({}))
    .unwrap();
  await store
    .dispatch(
      comparisonsApi.endpoints.comparisonsRetrieve.initiate({ id: "job" }),
    )
    .unwrap();
  jobStatus = "completed";
  await store
    .dispatch(
      comparisonsApi.endpoints.comparisonsRetrieve.initiate(
        { id: "job" },
        { forceRefetch: true, subscribe: false },
      ),
    )
    .unwrap();
  await settle();
  assert.equal(
    requests.filter((r) => new URL(r.url).pathname === "/api/comparisons")
      .length,
    2,
  );
  assert.equal(
    comparisonsApi.endpoints.comparisonsList.select({})(store.getState()).data
      ?.results[0].status,
    "completed",
  );
});

test("CSV and JSON downloads use owner session credentials, Blob URLs and release URLs after unsubscribe", async () => {
  const createUrl = URL.createObjectURL;
  const revokeUrl = URL.revokeObjectURL;
  const revoked: string[] = [];
  let allocated = 0;
  URL.createObjectURL = (blob) => {
    assert.ok(blob instanceof Blob);
    return `blob:download-${++allocated}`;
  };
  URL.revokeObjectURL = (url) => revoked.push(url);
  globalThis.fetch = async (input) => {
    const request = input as Request;
    requests.push(request);
    const isCsv = new URL(request.url).pathname.endsWith("answers.csv");
    return new Response(
      isCsv ? "id;status;answer;quote;file\n" : '{"protocol":"per_package"}',
      { headers: { "Content-Type": isCsv ? "text/csv" : "application/json" } },
    );
  };
  try {
    const csv = store.dispatch(
      comparisonsApi.endpoints.comparisonsAnswersRetrieve.initiate({
        id: "job",
        mode: "harness",
      }),
    );
    assert.equal(await csv.unwrap(), "blob:download-1");
    const report = store.dispatch(
      comparisonsApi.endpoints.comparisonsReportRetrieve.initiate({
        id: "job",
      }),
    );
    assert.equal(await report.unwrap(), "blob:download-2");
    assert.equal(new URL(requests[0].url).searchParams.get("mode"), "harness");
    assert.equal(
      new URL(requests[1].url).pathname,
      "/api/comparisons/job/report.json",
    );
    for (const request of requests) {
      assert.equal(request.credentials, "include");
      assert.equal(request.cache, "no-store");
      assert.equal(new URL(request.url).searchParams.has("token"), false);
    }
    csv.unsubscribe();
    report.unsubscribe();
    await new Promise((resolve) => setTimeout(resolve, 20));
    await settle();
    assert.deepEqual(revoked.sort(), ["blob:download-1", "blob:download-2"]);
  } finally {
    URL.createObjectURL = createUrl;
    URL.revokeObjectURL = revokeUrl;
  }
});
