"use client";

import { Printer } from "lucide-react";

export default function PrintButton() {
  return (
    <button
      onClick={() => window.print()}
      className="flex items-center gap-2 rounded-md border border-court-navy px-4 py-2 text-sm text-court-navy hover:bg-court-navy hover:text-white transition-colors"
    >
      <Printer className="h-4 w-4" />
      Print Docket
    </button>
  );
}
