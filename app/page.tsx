import type { Metadata } from "next";
import SearchScreen from "@/components/search/SearchScreen";

export const metadata: Metadata = {
  title: "Talent Dex",
};

// Screen 0: describe who you're hiring, then "Start scan" goes to /matches.
export default function Home() {
  return <SearchScreen />;
}
