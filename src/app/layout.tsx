import type { Metadata } from "next";
import "./globals.css";
import "./lib/envSetup";

export const metadata: Metadata = {
  title: "Atenxion Call Center Lab",
  description: "A realtime multi-agent telecom support demo with tool calls and handoffs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`antialiased`}>{children}</body>
    </html>
  );
}
