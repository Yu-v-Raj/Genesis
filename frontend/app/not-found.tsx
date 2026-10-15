import Link from "next/link";
import { Compass } from "lucide-react";

import { buttonClasses } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/feedback";

/** Unmatched URLs render inside the app shell, so the sidebar and command palette still work. */
export default function NotFound() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <EmptyState
        icon={Compass}
        title="This page doesn't exist"
        description="The link may be out of date. Use the navigation, or press ⌘K (Ctrl K) to search for a page."
        action={<Link href="/" className={buttonClasses("secondary", "sm")}>Go to Overview</Link>}
      />
    </div>
  );
}
