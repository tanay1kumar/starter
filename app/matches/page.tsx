import type { Metadata } from "next";
import { Suspense } from "react";
import DexApp from "@/components/dex/DexApp";
import { DexStatus } from "@/components/dex/DexStatus";

export const metadata: Metadata = {
  title: "Matches · Talent Dex",
};

export default function MatchesPage() {
  // useSearchParams() inside DexApp needs a Suspense boundary (Cache Components).
  return (
    <Suspense fallback={<DexStatus kind="loading" />}>
      <DexApp />
    </Suspense>
  );
}
