import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MedAssist",
  description: "Medical knowledge assistant with grounded, citation-backed answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-100 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
