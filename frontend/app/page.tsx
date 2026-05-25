// Root "/" is handled entirely by middleware.ts which redirects:
//   - unauthenticated → /queue
//   - authenticated   → role-specific home
// This file is a fallback that should never render in normal operation.
import { redirect } from "next/navigation";

export default function RootPage() {
  redirect("/queue");
}
