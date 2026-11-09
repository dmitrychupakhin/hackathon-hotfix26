import assert from "node:assert/strict";
import {
  access,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import {
  cleanGeneratedApi,
  publishGeneratedApi,
} from "../../../scripts/api/lib/output";

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "api-output-test-"));
  await mkdir(join(root, "account"));
  await writeFile(join(root, "account/index.ts"), "manual public entry");
  await writeFile(join(root, "base-api.ts"), "manual transport");
  await mkdir(join(root, "__generated__"));
  await writeFile(
    join(root, "__generated__/obsolete.ts"),
    "previous generated result",
  );
  return root;
}

async function assertManualFiles(root: string) {
  assert.equal(
    await readFile(join(root, "account/index.ts"), "utf8"),
    "manual public entry",
  );
  assert.equal(
    await readFile(join(root, "base-api.ts"), "utf8"),
    "manual transport",
  );
}

test("clean removes only generated files and succeeds when already absent", async () => {
  const root = await fixture();
  try {
    await cleanGeneratedApi(root);
    await assert.rejects(access(join(root, "__generated__")));
    await assertManualFiles(root);
    await cleanGeneratedApi(root);
    await assertManualFiles(root);
    await publishGeneratedApi(
      [{ path: "account/rtk.ts", content: "restored generated API" }],
      root,
    );
    assert.equal(
      await readFile(join(root, "__generated__/account/rtk.ts"), "utf8"),
      "restored generated API",
    );
    await assertManualFiles(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("publication fully replaces old artifacts without changing manual files", async () => {
  const root = await fixture();
  try {
    await publishGeneratedApi(
      [{ path: "account/rtk.ts", content: "new result" }],
      root,
    );
    await assert.rejects(access(join(root, "__generated__/obsolete.ts")));
    assert.equal(
      await readFile(join(root, "__generated__/account/rtk.ts"), "utf8"),
      "new result",
    );
    await assertManualFiles(root);
    assert.equal(
      (await readdir(root)).some((name) => name.startsWith(".api-generation-")),
      false,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("failed replacement restores the previous generated directory", async () => {
  const root = await fixture();
  try {
    const failPublication: typeof rename = async (source, destination) => {
      if (String(source).endsWith("/new"))
        throw new Error("Simulated publication failure");
      await rename(source, destination);
    };
    await assert.rejects(
      publishGeneratedApi(
        [{ path: "account/rtk.ts", content: "new result" }],
        root,
        failPublication,
      ),
      /Simulated publication failure/,
    );
    assert.equal(
      await readFile(join(root, "__generated__/obsolete.ts"), "utf8"),
      "previous generated result",
    );
    await assert.rejects(access(join(root, "__generated__/account/rtk.ts")));
    await assertManualFiles(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("invalid output paths preserve the previous generated directory", async () => {
  const root = await fixture();
  try {
    await assert.rejects(
      publishGeneratedApi(
        [{ path: "../base-api.ts", content: "must not overwrite" }],
        root,
      ),
      /Invalid generated file path/,
    );
    assert.equal(
      await readFile(join(root, "__generated__/obsolete.ts"), "utf8"),
      "previous generated result",
    );
    await assertManualFiles(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("mapping failure refreshes tag snapshot but preserves previous API and entrypoints", async () => {
  const root = await fixture();
  try {
    const { generateAndPublishApi } = await import(
      "../../../scripts/api/lib/generation"
    );
    await assert.rejects(
      generateAndPublishApi(
        {
          paths: {
            "/invalid": { get: { operationId: "invalid", tags: ["Unknown"] } },
          },
        },
        root,
      ),
      /Генерация API остановлена/,
    );
    assert.match(
      await readFile(join(root, "__generated__/schema-tags.ts"), "utf8"),
      /Unknown/,
    );
    assert.equal(
      await readFile(join(root, "__generated__/obsolete.ts"), "utf8"),
      "previous generated result",
    );
    await assertManualFiles(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("malformed schema preserves even the previous tag snapshot", async () => {
  const root = await fixture();
  try {
    await writeFile(
      join(root, "__generated__/schema-tags.ts"),
      "previous snapshot",
    );
    const { generateAndPublishApi } = await import(
      "../../../scripts/api/lib/generation"
    );
    await assert.rejects(
      generateAndPublishApi(
        { paths: { "/bad": { get: { tags: "invalid" } } } },
        root,
      ),
      /array of strings/,
    );
    assert.equal(
      await readFile(join(root, "__generated__/schema-tags.ts"), "utf8"),
      "previous snapshot",
    );
    assert.equal(
      await readFile(join(root, "__generated__/obsolete.ts"), "utf8"),
      "previous generated result",
    );
    await assertManualFiles(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
