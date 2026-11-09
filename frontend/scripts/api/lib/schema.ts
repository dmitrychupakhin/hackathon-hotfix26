import { join } from "node:path";
import ts from "typescript";
import { projectRoot } from "./output";

const methods = new Set([
  "get",
  "post",
  "put",
  "patch",
  "delete",
  "head",
  "options",
  "trace",
]);
export type SchemaOperation = {
  label: string;
  path: string;
  method: string;
  pathItem: Record<string, unknown>;
  definition: Record<string, unknown>;
  operationId?: string;
  tags: string[];
};

function object(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error(`${label}: expected an OpenAPI object`);
  return value as Record<string, unknown>;
}

export function readSchemaOperations(schema: unknown): SchemaOperation[] {
  const operations: SchemaOperation[] = [];
  const paths = object(object(schema, "Schema").paths, "Schema paths");
  for (const [path, item] of Object.entries(paths)) {
    const pathItem = object(item, path);
    for (const [method, value] of Object.entries(pathItem)) {
      if (!methods.has(method)) continue;
      const label = `${method.toUpperCase()} ${path}`;
      const operation = object(value, label);
      const tags = operation.tags === undefined ? [] : operation.tags;
      if (!Array.isArray(tags) || tags.some((tag) => typeof tag !== "string"))
        throw new Error(`${label}: tags must be an array of strings`);
      operations.push({
        label,
        path,
        method,
        pathItem,
        definition: operation,
        tags,
        operationId:
          typeof operation.operationId === "string"
            ? operation.operationId
            : undefined,
      });
    }
  }
  return operations;
}

export function analyzeApiModules(
  schema: unknown,
  modules: Readonly<Record<string, string>>,
) {
  const operations = readSchemaOperations(schema);
  const tags = [
    ...new Set(operations.flatMap((operation) => operation.tags)),
  ].sort();
  const entries = Object.entries(modules);
  const groupsForTag = (tag: string) =>
    entries.filter(([, value]) => value === tag).map(([group]) => group);
  const missing = tags
    .filter((tag) => groupsForTag(tag).length === 0)
    .map((tag) => ({
      tag,
      operations: operations
        .filter((operation) => operation.tags.includes(tag))
        .map((operation) => operation.label),
    }));
  const stale = entries
    .filter(([, tag]) => !tags.includes(tag))
    .map(([group, tag]) => ({ group, tag }));
  const duplicates = [...new Set(entries.map(([, tag]) => tag))]
    .filter((tag) => groupsForTag(tag).length > 1)
    .map((tag) => ({ tag, groups: groupsForTag(tag) }));
  const untagged = operations
    .filter((operation) => operation.tags.length === 0)
    .map((operation) => operation.label);
  const ambiguous = operations
    .filter(
      (operation) => new Set(operation.tags.flatMap(groupsForTag)).size > 1,
    )
    .map((operation) => operation.label);
  const contractErrors: string[] = [];
  const ids = new Set<string>();
  for (const operation of operations) {
    if (!operation.operationId)
      contractErrors.push(`${operation.label}: missing operationId`);
    else if (ids.has(operation.operationId))
      contractErrors.push(
        `${operation.label}: duplicate operationId ${operation.operationId}`,
      );
    else ids.add(operation.operationId);
  }
  const groups: Record<string, SchemaOperation[]> = Object.fromEntries(
    entries.map(([group]) => [group, []]),
  );
  for (const operation of operations) {
    const assigned = [...new Set(operation.tags.flatMap(groupsForTag))];
    if (
      assigned.length === 1 &&
      operation.tags.every((tag) => groupsForTag(tag).length > 0)
    )
      groups[assigned[0]].push(operation);
  }
  return {
    operations,
    groups,
    counts: Object.fromEntries(
      Object.entries(groups).map(([group, members]) => [group, members.length]),
    ),
    tags,
    groupCount: entries.length,
    matchedTagCount: tags.filter((tag) => groupsForTag(tag).length > 0).length,
    missing,
    stale,
    duplicates,
    untagged,
    ambiguous,
    contractErrors,
    valid:
      missing.length +
        stale.length +
        duplicates.length +
        untagged.length +
        ambiguous.length +
        contractErrors.length ===
      0,
  };
}

export function moduleForTags<T extends Readonly<Record<string, string>>>(
  tags: readonly string[] | undefined,
  label: string,
  modules: T,
): keyof T & string {
  const assigned = new Set<keyof T & string>();
  for (const tag of tags ?? []) {
    const groups = Object.entries(modules)
      .filter(([, value]) => value === tag)
      .map(([group]) => group as keyof T & string);
    if (groups.length === 0)
      throw new Error(`${label}: unknown OpenAPI tag "${tag}"`);
    for (const group of groups) assigned.add(group);
  }
  if (assigned.size !== 1)
    throw new Error(
      `${label}: expected exactly one API module, found ${assigned.size}`,
    );
  return [...assigned][0];
}

/** Preserve path-level parameters/metadata while selecting already parsed operations. */
export function schemaForModule(
  schema: unknown,
  report: ReturnType<typeof analyzeApiModules>,
  module: string,
) {
  const paths: Record<string, Record<string, unknown>> = {};
  for (const operation of report.groups[module] ?? []) {
    paths[operation.path] ??= Object.fromEntries(
      Object.entries(operation.pathItem).filter(([key]) => !methods.has(key)),
    );
    paths[operation.path][operation.method] = operation.definition;
  }
  return { ...(schema as Record<string, unknown>), paths };
}

/** Keep only components reachable from a module's document for Zod generation. */
export function schemaForZod(moduleSchema: ReturnType<typeof schemaForModule>) {
  const source = moduleSchema as Record<string, unknown>;
  const components =
    source.components === undefined
      ? {}
      : object(source.components, "components");
  const selected: Record<string, Record<string, unknown>> = {};
  const visited = new Set<string>();

  function includeComponent(category: string, name: string) {
    const key = JSON.stringify([category, name]);
    if (visited.has(key)) return;
    const group = object(components[category], `components.${category}`);
    if (!Object.hasOwn(group, name))
      throw new Error(`Missing component: ${category}/${name}`);
    visited.add(key);
    selected[category] ??= {};
    selected[category][name] = group[name];
    visit(group[name]);
  }

  function resolveReference(ref: string) {
    if (!ref.startsWith("#/"))
      throw new Error(`Unsupported unbundled reference: ${ref}`);
    const parts = ref
      .slice(2)
      .split("/")
      .map((part) =>
        decodeURIComponent(part).replace(/~1/g, "/").replace(/~0/g, "~"),
      );
    let current: unknown = source;
    for (const part of parts) {
      if (
        typeof current !== "object" ||
        current === null ||
        !Object.hasOwn(current, part)
      )
        throw new Error(`Unresolved reference: ${ref}`);
      current = (current as Record<string, unknown>)[part];
    }
    if (parts[0] === "components" && parts.length >= 3)
      includeComponent(parts[1], parts[2]);
  }

  function visit(value: unknown): void {
    if (Array.isArray(value)) {
      for (const item of value) visit(item);
    } else if (typeof value === "object" && value !== null) {
      const entry = value as Record<string, unknown>;
      if (typeof entry.$ref === "string") resolveReference(entry.$ref);
      if (Array.isArray(entry.security)) {
        for (const requirement of entry.security) {
          for (const name of Object.keys(
            object(requirement, "security requirement"),
          ))
            includeComponent("securitySchemes", name);
        }
      }
      for (const child of Object.values(entry)) visit(child);
    }
  }

  const document = Object.fromEntries(
    Object.entries(source).filter(([key]) => key !== "components"),
  );
  visit(document);
  return { ...document, components: selected };
}

export function renderSchemaTags(tags: readonly string[]) {
  return `// Generated from the latest OpenAPI schema by npm run api:generate. Do not edit.\nexport const openApiTags = ${JSON.stringify([...tags].sort(), null, 2)} as const;\nexport type OpenApiTag = (typeof openApiTags)[number];\n`;
}

export function formatApiModuleReport(
  report: ReturnType<typeof analyzeApiModules>,
) {
  const lines = [
    `OpenAPI: операций — ${report.operations.length}, тегов — ${report.tags.length}`,
    `apiModules: групп — ${report.groupCount}`,
    `Сопоставлено тегов: ${report.matchedTagCount}/${report.tags.length}`,
    `Не хватает сопоставлений: ${report.missing.length}`,
  ];
  for (const item of report.missing)
    lines.push(
      `  • ${item.tag} — операций: ${item.operations.length}`,
      ...item.operations.map((label) => `    ${label}`),
    );
  lines.push(`Устаревшие значения apiModules: ${report.stale.length}`);
  for (const item of report.stale)
    lines.push(`  • ${item.group}: ${JSON.stringify(item.tag)}`);
  lines.push(`Повторные назначения тегов: ${report.duplicates.length}`);
  for (const item of report.duplicates)
    lines.push(`  • ${item.tag}: ${item.groups.join(", ")}`);
  lines.push(
    `Операции без тегов: ${report.untagged.length}`,
    ...report.untagged.map((label) => `  • ${label}`),
  );
  lines.push(
    `Операции с неоднозначной группой: ${report.ambiguous.length}`,
    ...report.ambiguous.map((label) => `  • ${label}`),
  );
  if (report.contractErrors.length)
    lines.push(
      "Ошибки контракта:",
      ...report.contractErrors.map((error) => `  • ${error}`),
    );
  return lines.join("\n");
}

/** Check only the mapping and its type imports; SDK output may not exist yet. */
export function apiModuleTypeErrors(
  mappingFile = join(projectRoot, "api.config.ts"),
) {
  const program = ts.createProgram([mappingFile], {
    noEmit: true,
    strict: true,
    skipLibCheck: true,
    types: [],
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
  });
  return ts.getPreEmitDiagnostics(program).map((diagnostic) => {
    const message = ts.flattenDiagnosticMessageText(
      diagnostic.messageText,
      "\n",
    );
    if (!diagnostic.file || diagnostic.start === undefined)
      return `TS${diagnostic.code}: ${message}`;
    const { line, character } = diagnostic.file.getLineAndCharacterOfPosition(
      diagnostic.start,
    );
    return `${diagnostic.file.fileName}:${line + 1}:${character + 1} TS${diagnostic.code}: ${message}`;
  });
}
