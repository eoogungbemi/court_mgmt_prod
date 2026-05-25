import Navbar from "./Navbar";
import type { MeResponse } from "@/lib/types";

interface Props {
  user:     MeResponse | null;
  children: React.ReactNode;
  heading?: string;
  subheading?: string;
}

export default function PageLayout({ user, children, heading, subheading }: Props) {
  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar user={user} />

      <main className="mx-auto max-w-7xl px-4 py-6">
        {heading && (
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-court-navy">{heading}</h1>
            {subheading && <p className="mt-1 text-sm text-gray-500">{subheading}</p>}
          </div>
        )}
        {children}
      </main>

      <footer className="mt-12 border-t border-gray-200 py-4 text-center text-xs text-gray-400">
        Court of Common Pleas of Allegheny County · Family Division — Juvenile Branch · Pittsburgh, PA
      </footer>
    </div>
  );
}
