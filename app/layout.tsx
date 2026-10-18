import type { Metadata } from "next";
import { Fredoka, Geist_Mono, Nunito } from "next/font/google";
import "./globals.css";

// Design fonts: Fredoka (display), Nunito (body), Geist Mono (numbers).
const fredoka = Fredoka({ variable: "--font-fredoka", subsets: ["latin"], display: "swap" });
const nunito = Nunito({ variable: "--font-nunito", subsets: ["latin"], display: "swap" });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "Starter",
  description: "Find student builders from their hackathon projects and the code they actually wrote.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${fredoka.variable} ${nunito.variable} ${geistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
