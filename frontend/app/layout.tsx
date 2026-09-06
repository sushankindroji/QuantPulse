import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { TopContextBar } from "@/components/TopContextBar";

export const metadata: Metadata = {
  title: "QuantPulse — Quantitative Research Terminal",
  description: "Professional quantitative research platform for market data, alpha discovery, regime analysis, backtesting and execution research.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="ambient ambient-a" /><div className="ambient ambient-b" /><div className="ambient ambient-c" />
        <Sidebar />
        <main className="app-main">
          <TopContextBar />
          <div className="page-wrap">{children}</div>
        </main>
      </body>
    </html>
  );
}
