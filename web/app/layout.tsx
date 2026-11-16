import type { Metadata, Viewport } from "next";
import { Jost, Work_Sans } from "next/font/google";
import "./globals.css";

const jost = Jost({ variable: "--font-jost", subsets: ["latin"], weight: ["600", "700"] });
const work = Work_Sans({ variable: "--font-work", subsets: ["latin"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "mba jobs",
  description: "Jobs in India that suit an MBA, gathered every day from LinkedIn, Naukri, Indeed, IIMjobs and company sites.",
};

export const viewport: Viewport = {
  themeColor: "#F1F2F4",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${jost.variable} ${work.variable}`}>
      <body>{children}</body>
    </html>
  );
}
