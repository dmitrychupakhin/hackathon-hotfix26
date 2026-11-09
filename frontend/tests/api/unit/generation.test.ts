import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { test } from "node:test";
import { apiModules } from "../../../api.config";

for (const module of Object.keys(apiModules)) {
  test(`isolated ${module} import registers only its own endpoints`, () => {
    execFileSync(
      process.execPath,
      ["--import", "tsx", "tests/api/fixtures/import-api.ts", module],
      {
        cwd: process.cwd(),
        stdio: "pipe",
        timeout: 10_000,
      },
    );
  });
}

test("new schema operation automatically gains hooks, types, SDK method and public entries", async () => {
  const { mkdtemp, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { generateApiArtifacts } = await import(
    "../../../scripts/api/lib/generation"
  );
  const paths = Object.fromEntries(
    Object.entries(apiModules).map(([module, tag]) => [
      `/example/${module}`,
      {
        get: {
          operationId: `${module}Example`,
          tags: [tag],
          responses: {
            "200": {
              description: "OK",
              content: {
                "application/json": {
                  schema: {
                    type: "object",
                    properties: { value: { type: "string" } },
                    required: ["value"],
                  },
                },
              },
            },
          },
        },
      },
    ]),
  );
  paths["/example/account-new"] = {
    get: {
      operationId: "accountNewProbe",
      tags: [apiModules.account],
      responses: {
        "200": {
          description: "OK",
          content: {
            "application/json": {
              schema: {
                type: "object",
                properties: { value: { type: "string" } },
                required: ["value"],
              },
            },
          },
        },
      },
    },
  };
  const temporary = await mkdtemp(join(tmpdir(), "api-generation-test-"));
  try {
    const result = await generateApiArtifacts(
      { openapi: "3.0.3", info: { title: "Test", version: "1" }, paths },
      temporary,
    );
    const files = new Map(
      result.files.map((file) => [file.path, file.content]),
    );
    assert.equal(result.counts.account, 2);
    assert.match(
      files.get("account/client.ts") ?? "",
      /useAccountNewProbeQuery/,
    );
    assert.match(
      files.get("account/client.ts") ?? "",
      /AccountNewProbeApiResponse/,
    );
    assert.match(
      files.get("account/server.ts") ?? "",
      /accountNewProbe: async/,
    );
    assert.match(
      files.get("account/sdk/sdk.gen.ts") ?? "",
      /export const accountNewProbe/,
    );
    assert.match(files.get("account/server.ts") ?? "", /getAccountServerApi/);
    assert.match(
      files.get("account/sdk/types.gen.ts") ?? "",
      /AccountNewProbeResponse/,
    );
    assert.match(files.get("account/client.ts") ?? "", /schemas\/zod\.gen/);
    assert.match(
      files.get("account/schemas/zod.gen.ts") ?? "",
      /zAccountNewProbe/,
    );
    assert.doesNotMatch(
      files.get("account/schemas/zod.gen.ts") ?? "",
      /server-only/,
    );
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});
