import type { FieldPath, FieldValues, UseFormSetError } from "react-hook-form";
import { z } from "zod";

const objectSchema = z.record(z.string(), z.unknown());
const messagesSchema = z.array(z.string());

type Options<T extends FieldValues> = {
  error: unknown;
  setError: UseFormSetError<T>;
  fields: readonly FieldPath<T>[];
  fallback: string;
  schema?: z.ZodType;
  onRootError?: (message: string) => void;
};

/** Adapt RTK Query errors to a form without assuming the server response is valid. */
export function applyApiFormErrors<T extends FieldValues>({
  error,
  setError,
  fields,
  fallback,
  schema,
  onRootError,
}: Options<T>) {
  const envelope = objectSchema.safeParse(error);
  let body: unknown = envelope.success ? envelope.data.data : undefined;
  if (schema) {
    const parsed = schema.safeParse(body);
    body = parsed.success ? parsed.data : undefined;
  }
  const parsed = objectSchema.safeParse(body);
  const data = parsed.success ? parsed.data : {};
  let hasFieldErrors = false;
  for (const field of fields) {
    const messages = messagesSchema.safeParse(data[field]);
    if (!messages.success) continue;
    const message = messages.data.filter((item) => item.trim()).join(" ");
    if (!message) continue;
    setError(field, { type: "server", message });
    hasFieldErrors = true;
  }
  const detail = messagesSchema.safeParse(data.detail ?? data.non_field_errors);
  const message = detail.success
    ? detail.data.filter((item) => item.trim()).join(" ")
    : "";
  if (message || !hasFieldErrors) {
    if (onRootError) onRootError(fallback);
    setError("root", { type: "server", message: message || fallback });
  }
}
