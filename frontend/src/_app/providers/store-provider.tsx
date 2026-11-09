"use client";

import { setupListeners } from "@reduxjs/toolkit/query";
import { type ReactNode, useEffect, useRef } from "react";
import { Provider } from "react-redux";
import { type AppStore, makeStore } from "../store/store";

export function StoreProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<AppStore | null>(null);
  if (storeRef.current === null) storeRef.current = makeStore();
  const store = storeRef.current;

  useEffect(() => setupListeners(store.dispatch), [store]);

  return <Provider store={store}>{children}</Provider>;
}
