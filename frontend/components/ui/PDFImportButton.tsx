"use client";

import { useState } from "react";
import { FileUp } from "lucide-react";
import Button from "@/components/ui/Button";
import PDFImportModal from "@/components/ui/PDFImportModal";

export default function PDFImportButton({ onImported }: { onImported?: () => void }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <FileUp className="h-4 w-4 mr-1.5" />
        Import PDF docket
      </Button>

      {open && (
        <PDFImportModal
          onClose={() => setOpen(false)}
          onImported={() => { setOpen(false); onImported?.(); }}
        />
      )}
    </>
  );
}
