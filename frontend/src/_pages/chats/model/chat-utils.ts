export function chatError(error: unknown): string {
  if (typeof error === "object" && error !== null && "data" in error) {
    const data = error.data;
    if (typeof data === "object" && data !== null) {
      return (
        Object.values(data)
          .flat()
          .filter((item) => typeof item === "string")
          .join(" ") || "Не удалось выполнить запрос."
      );
    }
    if ("status" in error && error.status === 401)
      return "Сессия истекла. Войдите снова.";
  }
  return "Не удалось выполнить запрос. Проверьте соединение и попробуйте снова.";
}
export const isActiveRun = (status?: string) =>
  ["pending", "queued", "running"].includes(status ?? "");
