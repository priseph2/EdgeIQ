import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "EdgeIQ — Sports Betting Intelligence",
  description: "AI-powered predictions, odds comparison, value bets, bet tracker",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full flex flex-col bg-[#080e1e] text-slate-200 antialiased">
        <Nav />
        <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
