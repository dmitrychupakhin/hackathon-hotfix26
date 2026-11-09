import assert from "node:assert/strict";
import { test } from "node:test";
import type { UseFormSetError } from "react-hook-form";
import { z } from "zod";
import { applyApiFormErrors } from "../../../src/shared/utils/apply-api-form-errors";

type Fields = { email: string; password: string };

function errorsFor(error: unknown, schema?: z.ZodType) {
  const errors: Record<string, string | undefined> = {};
  const setError: UseFormSetError<Fields> = (name, value) => {
    errors[name] = value.message;
  };
  applyApiFormErrors({
    error,
    setError,
    fields: ["email", "password"],
    fallback: "Ошибка запроса",
    schema,
  });
  return errors;
}

test("form errors map fields and detail independently", () => {
  assert.deepEqual(
    errorsFor({
      status: 400,
      data: {
        email: ["Email занят"],
        password: ["Первая", "Вторая"],
        detail: ["Общая ошибка"],
      },
    }),
    { email: "Email занят", password: "Первая Вторая", root: "Общая ошибка" },
  );
  assert.deepEqual(
    errorsFor({
      status: 400,
      data: { email: ["Email занят"], unknown: ["Неизвестно"] },
    }),
    { email: "Email занят" },
  );
});

test("form errors use fallback for unknown, empty and malformed responses", () => {
  for (const error of [
    null,
    { status: "FETCH_ERROR" },
    { data: { detail: [] } },
    { data: { email: [42] } },
    { data: { unknown: ["Ошибка"] } },
  ]) {
    assert.deepEqual(errorsFor(error), { root: "Ошибка запроса" });
  }
});

test("form errors support a generated schema", () => {
  const schema = z.object({ detail: z.array(z.string()) });
  assert.deepEqual(
    errorsFor({ data: { detail: ["Неверный пароль"] } }, schema),
    { root: "Неверный пароль" },
  );
  assert.deepEqual(errorsFor({ data: { email: ["Ошибка"] } }, schema), {
    root: "Ошибка запроса",
  });
});

test("notification errors use UI fallback instead of server detail", () => {
  for (const data of [
    { detail: ["Internal server detail"] },
    { non_field_errors: ["Internal server detail"] },
  ]) {
    const notifications: string[] = [];
    const formErrors: Record<string, string | undefined> = {};
    applyApiFormErrors<Fields>({
      error: { data },
      setError: (name, error) => {
        formErrors[name] = error.message;
      },
      fields: ["email", "password"],
      fallback: "Не удалось выполнить действие",
      onRootError: (message) => notifications.push(message),
    });
    assert.deepEqual(notifications, ["Не удалось выполнить действие"]);
    assert.deepEqual(formErrors, { root: "Internal server detail" });
  }
});
