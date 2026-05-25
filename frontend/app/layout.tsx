import type { Metadata } from "next";
import "./globals.css";

const courtName = process.env.NEXT_PUBLIC_COURT_NAME ?? "Allegheny County Juvenile Court";

export const metadata: Metadata = {
  title:       `${courtName} — Case Management`,
  description: `${courtName} · Case Management System`,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
