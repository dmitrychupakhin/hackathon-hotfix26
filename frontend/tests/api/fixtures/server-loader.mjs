// Test-only replacements for Next's request context and server-only marker.
import { AsyncLocalStorage } from "node:async_hooks";
import { registerHooks } from "node:module";

export const requestCookies = new AsyncLocalStorage();
const cookieContextKey = Symbol.for("api-server-tests.cookies");
globalThis[cookieContextKey] = requestCookies;
const cookieStub = `export async function cookies() {
  return { toString: () => globalThis[Symbol.for("api-server-tests.cookies")].getStore() ?? "" };
}`;

registerHooks({
  load(url, context, nextLoad) {
    if (url.startsWith("data:text/javascript,")) {
      return {
        format: "module",
        source: decodeURIComponent(url.slice("data:text/javascript,".length)),
        shortCircuit: true,
      };
    }
    return nextLoad(url, context);
  },
  resolve(specifier, context, nextResolve) {
    if (specifier === "server-only") {
      return {
        url: "data:text/javascript,export {};",
        format: "module",
        shortCircuit: true,
      };
    }
    if (specifier === "next/headers") {
      return {
        url: `data:text/javascript,${encodeURIComponent(cookieStub)}`,
        format: "module",
        shortCircuit: true,
      };
    }
    return nextResolve(specifier, context);
  },
});
