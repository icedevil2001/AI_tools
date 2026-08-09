import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Food & symptom diary",
  description: "Log meals and symptoms to help spot patterns.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Food diary",
  },
};

export const viewport: Viewport = {
  themeColor: "#faf7f2",
  width: "device-width",
  initialScale: 1,
  // Zoom stays enabled deliberately: this is used by someone who sometimes
  // can't focus their eyes properly, and disabling pinch-zoom would be a
  // genuine accessibility failure.
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh bg-cream text-ink antialiased">{children}</body>
    </html>
  );
}
