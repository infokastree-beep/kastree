import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import { DM_Sans, Fraunces } from "next/font/google";
import { AppProviders } from "@/components/providers/AppProviders";
import "./globals.css";

const sans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Kastree",
  applicationName: "Kastree",
  description: "Financial intelligence for accounting practices",
  // 16px tab icon is a pixel-fit bar mark (3px bars, 2px gaps). Do not
  // point the favicon at the full-resolution lockup — downscaling it
  // closes the gaps and the three bars merge.
  icons: {
    icon: [
      { url: "/favicon.ico?v=4", sizes: "16x16" },
      { url: "/icon-16.png?v=4", type: "image/png", sizes: "16x16" },
      { url: "/icon.png?v=4", type: "image/png", sizes: "32x32" },
      { url: "/icon-192.png?v=4", type: "image/png", sizes: "192x192" },
    ],
    apple: [
      {
        url: "/apple-touch-icon.png?v=4",
        sizes: "180x180",
        type: "image/png",
      },
    ],
  },
  other: {
    // Public, unauthenticated marker for CI: curl www.kastree.ie | grep kastree-git-sha
    "kastree-git-sha": process.env.NEXT_PUBLIC_GIT_SHA ?? "dev",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable}`}>
      <body className="font-sans">
        <AppProviders>{children}</AppProviders>
        <Analytics />
      </body>
    </html>
  );
}
