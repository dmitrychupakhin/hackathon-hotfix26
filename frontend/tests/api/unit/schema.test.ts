import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { apiModules } from "../../../api.config";
import {
  analyzeApiModules,
  apiModuleTypeErrors,
  formatApiModuleReport,
  moduleForTags,
  renderSchemaTags,
  schemaForModule,
  schemaForZod,
} from "../../../scripts/api/lib/schema";

const knownTags = Object.values(apiModules);
const schema = (tags: string[]) => ({
  paths: Object.fromEntries(
    tags.map((tag, index) => [
      `/operation-${index}`,
      { get: { operationId: `operation${index}`, tags: [tag] } },
    ]),
  ),
});

test("Zod document retains transitive, cyclic, shared and security components only", () => {
  const document = {
    openapi: "3.0.3",
    paths: {
      "/auth": {
        post: {
          operationId: "login",
          tags: [apiModules.auth],
          security: [{ bearer: [] }],
          requestBody: { $ref: "#/components/requestBodies/Input" },
          responses: { "401": { $ref: "#/components/responses/Error" } },
        },
      },
    },
    components: {
      requestBodies: {
        Input: {
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/Login~1Input" },
            },
          },
        },
      },
      responses: {
        Error: {
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/Shared" },
            },
          },
        },
      },
      schemas: {
        "Login/Input": {
          properties: { nested: { $ref: "#/components/schemas/Shared" } },
        },
        Shared: {
          properties: { parent: { $ref: "#/components/schemas/Login~1Input" } },
        },
        Unused: { type: "string" },
      },
      securitySchemes: {
        bearer: { type: "http", scheme: "bearer" },
        unused: { type: "http", scheme: "basic" },
      },
    },
  };
  const result = schemaForZod(
    schemaForModule(document, analyzeApiModules(document, apiModules), "auth"),
  );
  assert.deepEqual(Object.keys(result.components.schemas).sort(), [
    "Login/Input",
    "Shared",
  ]);
  assert.deepEqual(Object.keys(result.components.securitySchemes), ["bearer"]);
  assert.deepEqual(Object.keys(result.components.requestBodies), ["Input"]);
  assert.deepEqual(Object.keys(result.components.responses), ["Error"]);
  assert.equal(Object.keys(document.components.schemas).length, 3);
});

test("Zod document rejects unresolved references", () => {
  const document = {
    paths: {
      "/auth": {
        post: {
          operationId: "login",
          tags: [apiModules.auth],
          requestBody: { $ref: "#/components/schemas/Missing" },
        },
      },
    },
    components: { schemas: {} },
  };
  assert.throws(
    () =>
      schemaForZod(
        schemaForModule(
          document,
          analyzeApiModules(document, apiModules),
          "auth",
        ),
      ),
    /Unresolved reference/,
  );
});

test("complete mapping reports every operation and tag", () => {
  const report = analyzeApiModules(schema(knownTags), apiModules);
  assert.equal(report.valid, true);
  assert.equal(report.operations.length, knownTags.length);
  assert.equal(report.matchedTagCount, knownTags.length);
  assert.equal(report.missing.length, 0);
  assert.match(formatApiModuleReport(report), /Не хватает сопоставлений: 0/);
});

test("all new backend tags are reported with operation counts", () => {
  const report = analyzeApiModules(
    schema([...knownTags, "Документы", "Отчёты", "Документы"]),
    apiModules,
  );
  assert.equal(report.valid, false);
  assert.equal(report.missing.length, 2);
  assert.equal(report.matchedTagCount, knownTags.length);
  assert.equal(
    report.missing.find((item) => item.tag === "Документы")?.operations.length,
    2,
  );
  const text = formatApiModuleReport(report);
  assert.match(text, /Не хватает сопоставлений: 2/);
  assert.match(text, /Документы — операций: 2/);
  assert.match(text, /Отчёты — операций: 1/);
});

test("removed or misspelled tags and duplicate assignments are reported", () => {
  const typo = analyzeApiModules(schema(knownTags), {
    ...apiModules,
    account: "Опечатка",
  });
  assert.equal(typo.valid, false);
  assert.deepEqual(typo.stale, [{ group: "account", tag: "Опечатка" }]);
  assert.deepEqual(
    typo.missing.map((item) => item.tag),
    [apiModules.account],
  );
  const duplicate = analyzeApiModules(schema(knownTags), {
    ...apiModules,
    duplicateAuth: apiModules.auth,
  });
  assert.equal(duplicate.valid, false);
  assert.deepEqual(duplicate.duplicates, [
    { tag: apiModules.auth, groups: ["auth", "duplicateAuth"] },
  ]);
});

test("untagged and ambiguous operations are collected together", () => {
  const document = {
    paths: {
      "/without-tag": { get: { operationId: "withoutTag" } },
      "/two-groups": {
        get: {
          operationId: "twoGroups",
          tags: [apiModules.auth, apiModules.account],
        },
      },
    },
  };
  const report = analyzeApiModules(document, apiModules);
  assert.equal(report.valid, false);
  assert.deepEqual(report.untagged, ["GET /without-tag"]);
  assert.deepEqual(report.ambiguous, ["GET /two-groups"]);
});

test("snapshot uses only operation tags and is deterministic", () => {
  const document = {
    ...schema([...knownTags].reverse()),
    tags: [{ name: "Unused documentation tag" }],
  };
  const report = analyzeApiModules(document, apiModules);
  assert.equal(report.tags.includes("Unused documentation tag"), false);
  assert.equal(
    renderSchemaTags(report.tags),
    renderSchemaTags([...report.tags].reverse()),
  );
  assert.match(renderSchemaTags(report.tags), /export type OpenApiTag/);
  assert.throws(
    () =>
      analyzeApiModules(
        { paths: { "/bad": { get: { operationId: "bad", tags: null } } } },
        apiModules,
      ),
    /array of strings/,
  );
});

test("mapping typecheck needs only the snapshot and detects invalid values and missing coverage", async () => {
  const root = await mkdtemp(join(tmpdir(), "api-tags-types-"));
  try {
    const mappingFile = join(root, "api.config.ts");
    const source = (await readFile("api.config.ts", "utf8")).replace(
      "./src/shared/api/__generated__/schema-tags",
      "./schema-tags",
    );
    await writeFile(mappingFile, source);
    await writeFile(join(root, "schema-tags.ts"), renderSchemaTags(knownTags));
    assert.deepEqual(apiModuleTypeErrors(mappingFile), []);
    await writeFile(
      mappingFile,
      source.replace('account: "Личный кабинет"', 'account: "Опечатка"'),
    );
    assert.ok(
      apiModuleTypeErrors(mappingFile).some((error) =>
        error.includes("Опечатка"),
      ),
    );
    await writeFile(mappingFile, source);
    await writeFile(
      join(root, "schema-tags.ts"),
      renderSchemaTags([...knownTags, "Новая группа"]),
    );
    assert.ok(
      apiModuleTypeErrors(mappingFile).some(
        (error) => error.includes("Новая группа") && error.includes("never"),
      ),
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

const schemaWithOperations = (operations: Record<string, unknown>) => ({
  paths: { "/example": operations },
});

test("OpenAPI tags map to exactly one module", () => {
  assert.equal(moduleForTags(["Авторизация"], "login", apiModules), "auth");
  assert.equal(
    moduleForTags(["Регистрация"], "register", apiModules),
    "registration",
  );
  assert.equal(moduleForTags(["Личный кабинет"], "me", apiModules), "account");
  assert.equal(moduleForTags(["Пользователи"], "user", apiModules), "users");
  assert.throws(
    () => moduleForTags(undefined, "missing", apiModules),
    /exactly one/,
  );
  assert.throws(() => moduleForTags([], "empty", apiModules), /exactly one/);
  assert.throws(
    () => moduleForTags(["New"], "unknown", apiModules),
    /unknown OpenAPI tag/,
  );
  assert.throws(
    () => moduleForTags(["Авторизация", "New"], "mixed", apiModules),
    /unknown OpenAPI tag/,
  );
  assert.throws(
    () =>
      moduleForTags(["Авторизация", "Регистрация"], "ambiguous", apiModules),
    /exactly one/,
  );
});

test("schema validation rejects duplicate/missing operationId and malformed tags", () => {
  assert.match(
    analyzeApiModules(
      schemaWithOperations({ get: { tags: [apiModules.users] } }),
      apiModules,
    ).contractErrors.join("\n"),
    /missing operationId/,
  );
  assert.match(
    analyzeApiModules(
      schemaWithOperations({
        get: { operationId: "duplicate", tags: [apiModules.users] },
        post: { operationId: "duplicate", tags: [apiModules.auth] },
      }),
      apiModules,
    ).contractErrors.join("\n"),
    /duplicate operationId/,
  );
  assert.throws(
    () =>
      analyzeApiModules(
        schemaWithOperations({
          get: { operationId: "bad", tags: apiModules.users },
        }),
        apiModules,
      ),
    /array of strings/,
  );
  assert.deepEqual(
    analyzeApiModules(
      schemaWithOperations({
        get: { operationId: "user", tags: [apiModules.users] },
      }),
      apiModules,
    ).counts,
    {
      ...Object.fromEntries(
        Object.keys(apiModules).map((module) => [module, 0]),
      ),
      users: 1,
    },
  );
});

test("module schemas preserve path metadata and select only assigned methods", () => {
  const parameters = [
    { name: "id", in: "path", required: true, schema: { type: "string" } },
  ];
  const document = {
    paths: {
      "/users/{id}": {
        parameters,
        summary: "Shared path",
        get: { operationId: "read", tags: [apiModules.users] },
        post: { operationId: "write", tags: [apiModules.account] },
      },
    },
  };
  const report = analyzeApiModules(document, apiModules);
  assert.deepEqual(schemaForModule(document, report, "users").paths, {
    "/users/{id}": {
      parameters,
      summary: "Shared path",
      get: document.paths["/users/{id}"].get,
    },
  });
  assert.throws(
    () =>
      moduleForTags([apiModules.auth], "duplicate", {
        ...apiModules,
        duplicate: apiModules.auth,
      }),
    /exactly one/,
  );
});
