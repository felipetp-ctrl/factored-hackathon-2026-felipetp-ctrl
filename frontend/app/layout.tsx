import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LATAM Bank Disputes",
  description: "Card-charge dispute service: the customer app and the bank side, side by side, with guided scenarios.",
};

// Fonts load from Google Fonts at runtime (with a system fallback) instead of next/font, so the build never
// depends on fetching font files.
const FONTS = "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link rel="stylesheet" href={FONTS} />
      </head>
      <body>{children}</body>
    </html>
  );
}
