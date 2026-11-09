import type { Metadata } from "next";
import localFont from "next/font/local";
import { Suspense } from "react";
import { NotificationProvider } from "@/shared/ui/notification-provider";
import "../styles/globals.css";
import { StoreProvider } from "../providers/store-provider";

const golosText = localFont({
  src: "../../shared/assets/fonts/GolosText-VariableFont_wght.ttf",
  variable: "--font-golos-text",
  weight: "400 900",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Betelgeuse — факты вместо догадок",
    template: "%s | Betelgeuse",
  },
  description:
    "Помощник по закупкам, который подтверждает ответы источниками и цитатами из документов.",
};

export function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${golosText.variable} h-full font-sans antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* RTK initializes random IDs; Cache Components must defer this subtree. */}
        <Suspense fallback={null}>
          <StoreProvider>
            <NotificationProvider>{children}</NotificationProvider>
          </StoreProvider>
        </Suspense>
      </body>
    </html>
  );
}
