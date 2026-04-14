import type { Metadata } from "next";
import { DM_Sans, Caveat } from "next/font/google";
import "./globals.css";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
});

const caveat = Caveat({
  subsets: ["latin"],
  variable: "--font-caveat",
});

export const metadata: Metadata = {
  title: "InkClone - Your handwriting, digitally replicated",
  description: "Type anything and get a realistic handwritten document. Professional quality with authentic handwriting simulation.",
  keywords: "handwriting, text conversion, documents, AI, automation, realistic handwriting",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${dmSans.variable} ${caveat.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}