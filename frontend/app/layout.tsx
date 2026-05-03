import type { Metadata } from "next";
import { DM_Sans, Fira_Code } from "next/font/google";
import "./globals.css";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const geistMono = Fira_Code({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  weight: ["300", "400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "PrepQ — AI Interview Prep for Indian Students",
  description:
    "PrepQ is an AI-powered interview preparation strategist for Indian students and freshers. Get a ruthlessly focused, personalized prep plan for your exact company, role, and timeline.",
  keywords: [
    "interview preparation",
    "AI interview prep",
    "Indian students",
    "freshers interview",
    "TCS interview",
    "Infosys interview",
    "placement prep",
    "PrepQ",
  ],
  openGraph: {
    title: "PrepQ — AI Interview Prep",
    description: "Personalized interview prep plans powered by AI. Built for Indian students.",
    type: "website",
    siteName: "PrepQ",
  },
  twitter: {
    card: "summary_large_image",
    title: "PrepQ — AI Interview Prep",
    description: "Personalized interview prep plans powered by AI.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${dmSans.variable} ${geistMono.variable}`}>
      <head>
        <meta name="theme-color" content="#080808" />
      </head>
      <body className="bg-surface-0 text-text-primary antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
