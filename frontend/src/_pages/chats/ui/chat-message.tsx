import type { ReactNode } from "react";

export function ChatMessage({
  children,
  time,
  sender,
}: {
  children: ReactNode;
  time: string;
  sender: "user" | "assistant";
}) {
  const isUser = sender === "user";
  return (
    <div
      className={
        isUser
          ? "ml-auto max-w-full rounded-xl bg-accent-100 px-5 py-3.5 text-body-base"
          : "w-full max-w-[830px] rounded-xl bg-content-50 px-5 py-4 text-body-base"
      }
    >
      <div className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
        {children}
      </div>
      <p
        className={`${isUser ? "mt-[7px] " : ""}text-right text-[10px] leading-3`}
      >
        {time}
      </p>
    </div>
  );
}
