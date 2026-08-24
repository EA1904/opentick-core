import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradoVera — Analytics & Simulation Trading Platform",
  description: "Réplique complète de Tradovate en local/SaaS avec données 100% gratuites.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr" className="dark">
      <body className="min-h-screen antialiased selection:bg-indigo-500 selection:text-white">
        {children}
      </body>
    </html>
  );
}
