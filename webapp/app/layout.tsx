import type { Metadata } from "next";
import Script from "next/script";
import { Header } from "@/components/header";
import { Footer } from "@/components/footer";
import { MobileStickyCTA } from "@/components/mobile-sticky-cta";
import { DocumentLanguage } from "@/components/document-language";
import "./globals.css";
import "@fontsource-variable/inter";
import "@fontsource-variable/noto-sans-devanagari";

export const metadata: Metadata = {
  metadataBase: new URL("https://indiankumbh.com"),
  title: { default: "IndianKumbh — Guides for All Kumbh Melas in India", template: "%s | IndianKumbh" },
  description: "One trusted guide for Ujjain, Nashik-Trimbakeshwar, Prayagraj and Haridwar Kumbh Melas.",
  keywords: ["Indian Kumbh", "Ujjain Simhastha 2028", "Nashik Kumbh 2027", "Prayagraj Kumbh", "Haridwar Kumbh"],
  openGraph: {
    title: "IndianKumbh — One Trusted Guide for All Kumbh Melas",
    description: "Currently focused on Ujjain Simhastha 2028, with national guides being built.",
    images: ["/images/ujjain-shipra-hero.png"],
    type: "website",
  },
  twitter: { card: "summary_large_image" },
};

const travelSchema = {
  "@context": "https://schema.org",
  "@type": "TravelGuide",
  name: "IndianKumbh",
  description: "Practical multilingual planning for India's four sacred Kumbh cities.",
  about: ["Ujjain", "Nashik-Trimbakeshwar", "Prayagraj", "Haridwar"].map((name) => ({ "@type": "TouristDestination", name })),
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <DocumentLanguage />
        <Header />
        {children}
        <Footer />
        <MobileStickyCTA />
        <Script id="travel-guide-schema" type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(travelSchema) }} />
        {/* Google Analytics placeholder: replace G-XXXXXXXXXX and enable when ready. */}
        <Script src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX" strategy="afterInteractive" />
        <Script id="google-analytics" strategy="afterInteractive">{`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag('js',new Date());gtag('config','G-XXXXXXXXXX');`}</Script>
      </body>
    </html>
  );
}
