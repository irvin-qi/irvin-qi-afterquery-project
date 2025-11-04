import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ReactQueryClientProvider } from "@/providers/react-query-provider";
import { SupabaseProvider } from "@/providers/supabase-provider";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Afterquery Interview Platform",
  description: "Admin and candidate experience for coding assessments",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="bg-zinc-50 text-zinc-900">
        <ReactQueryClientProvider>
          <SupabaseProvider>{children}</SupabaseProvider>
        </ReactQueryClientProvider>
      </body>
    </html>
  );
}
