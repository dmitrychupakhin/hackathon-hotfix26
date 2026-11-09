const protectedPaths = [
  "/chats",
  "/prompt",
  "/comparisons",
  "/profile",
  "/change-email",
  "/change-password",
];

export function isProtectedPath(pathname: string) {
  return protectedPaths.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
}

/** Only local workspace URLs can be used as an authentication return target. */
export function safeReturnPath(value: string | null | undefined) {
  if (
    !value ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    Array.from(value).some(
      (character) =>
        character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127,
    )
  )
    return "/profile";
  try {
    const parsed = new URL(value, "https://workspace.invalid");
    if (
      parsed.origin !== "https://workspace.invalid" ||
      !isProtectedPath(parsed.pathname)
    )
      return "/profile";
    return parsed.pathname + parsed.search + parsed.hash;
  } catch {
    return "/profile";
  }
}

export function loginPath(returnTo: string) {
  const target = new URL(safeReturnPath(returnTo), "https://workspace.invalid");
  // The quote fragment stays in the browser, including during an auth round
  // trip; copying it into next would put document text in HTTP access logs.
  const query = new URLSearchParams({ next: target.pathname + target.search });
  return `/login?${query}${target.hash}`;
}

export function afterLoginPath(search: string, hash = "") {
  const returnTo = safeReturnPath(new URLSearchParams(search).get("next"));
  // URL fragments do not reach the server. Browsers retain the source fragment
  // across a redirect without an explicit fragment; carry it back after login.
  return returnTo.includes("#") || !hash.startsWith("#")
    ? returnTo
    : returnTo + hash;
}
