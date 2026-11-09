import { mkdir, mkdtemp, rename, rm, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve, sep } from "node:path";

// Resolve from this script, never from a user-supplied directory or shell cwd.
export const projectRoot = resolve(__dirname, "../../..");
export const apiRoot = join(projectRoot, "src/shared/api");

export type GeneratedFile = { path: string; content: string };

/** Diagnostic metadata refreshes independently from the last successful API. */
export async function publishSchemaTags(content: string, root = apiRoot) {
  const target = join(root, "__generated__");
  await mkdir(target, { recursive: true });
  const temporary = await mkdtemp(join(root, ".api-tags-"));
  try {
    const staged = join(temporary, "schema-tags.ts");
    await writeFile(staged, content);
    await rename(staged, join(target, "schema-tags.ts"));
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

export async function cleanGeneratedApi(root = apiRoot) {
  await rm(join(root, "__generated__"), { recursive: true, force: true });
}

export async function publishGeneratedApi(
  files: GeneratedFile[],
  root = apiRoot,
  renameDirectory = rename,
) {
  await mkdir(root, { recursive: true });
  const transaction = await mkdtemp(join(root, ".api-generation-"));
  const incoming = join(transaction, "new");
  const backup = join(transaction, "old");
  const target = join(root, "__generated__");
  let preserveBackup = false;
  try {
    await mkdir(incoming);
    for (const file of files) {
      const output = resolve(incoming, file.path);
      if (isAbsolute(file.path) || !output.startsWith(`${incoming}${sep}`)) {
        throw new Error(`Invalid generated file path: ${file.path}`);
      }
      await mkdir(dirname(output), { recursive: true });
      await writeFile(output, file.content);
    }
    let backedUp = false;
    try {
      await renameDirectory(target, backup);
      backedUp = true;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    try {
      await renameDirectory(incoming, target);
    } catch (error) {
      if (backedUp) {
        try {
          await renameDirectory(backup, target);
        } catch (rollbackError) {
          preserveBackup = true;
          throw new AggregateError(
            [error, rollbackError],
            `Could not restore generated API. Backup retained at ${backup}`,
          );
        }
      }
      throw error;
    }
  } finally {
    if (!preserveBackup)
      await rm(transaction, { recursive: true, force: true });
  }
}
