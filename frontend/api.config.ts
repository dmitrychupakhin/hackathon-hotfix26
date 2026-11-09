import type { OpenApiTag } from "./src/shared/api/__generated__/schema-tags";

export const apiSchemaUrl = "https://company-corp.ru/api/schema/";

export const apiModules = {
  auth: "Авторизация",
  registration: "Регистрация",
  account: "Личный кабинет",
  users: "Пользователи",
  chats: "Чаты",
  comparisons: "Сравнения",
} as const satisfies Record<string, OpenApiTag>;

export type ApiModule = keyof typeof apiModules;

type AssertAllTagsMapped<T extends never> = T;
/** A compiler error here lists backend tags still missing from apiModules. */
export type MissingApiModuleTags = AssertAllTagsMapped<
  Exclude<OpenApiTag, (typeof apiModules)[ApiModule]>
>;
