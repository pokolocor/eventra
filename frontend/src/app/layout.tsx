import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Eventra — From Events to Execution",
  description:
    "Eventra is an autonomous, event-driven trading agent. Qwen interprets market events, a deterministic risk engine gates every decision, and trades execute in a paper portfolio.",
  applicationName: "Eventra",
};

export const viewport: Viewport = {
  themeColor: "#070a0f",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
