// IP — Caramurú Construções — assinatura do autor

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Centro de comando — Caramurú Construções",
  description: "Avanço físico, diário de obra, segurança e ativos em campo.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
