import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Podcast Search",
  description: "Search and chat with podcast transcripts",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="min-h-screen bg-background">
          <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="container flex h-14 items-center justify-between">
              <div className="flex items-center">
                <a href="/" className="flex items-center space-x-2">
                  <span className="font-bold text-xl">Podcast Search</span>
                </a>
              </div>
              <nav className="flex items-center space-x-6 text-sm font-medium">
                <a
                  href="/"
                  className="transition-colors hover:text-foreground/80 text-foreground/60"
                >
                  Search
                </a>
                <a
                  href="/podcasts"
                  className="transition-colors hover:text-foreground/80 text-foreground/60"
                >
                  Podcasts
                </a>
                <a
                  href="/chat"
                  className="transition-colors hover:text-foreground/80 text-foreground/60"
                >
                  Chat
                </a>
                <a
                  href="/admin"
                  className="transition-colors hover:text-foreground/80 text-foreground/60"
                >
                  Studio
                </a>
              </nav>
            </div>
          </header>
          <main>{children}</main>
        </div>
        <Toaster />
      </body>
    </html>
  );
}
