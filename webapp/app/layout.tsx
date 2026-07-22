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
  title: { default: "IndianKumbh — India’s Practical Pilgrimage Travel Guide", template: "%s | IndianKumbh" },
  description: "India’s practical pilgrimage travel guide for Kumbh Mela, Char Dham, 12 Jyotirlinga, temple circuits and sacred city travel.",
  keywords: ["Indian pilgrimage travel", "Kumbh Mela", "Char Dham Yatra", "12 Jyotirlinga", "temple circuits", "sacred cities"],
  openGraph: {
    title: "IndianKumbh — India’s Practical Pilgrimage Travel Guide",
    description: "Kumbh Mela, Char Dham, 12 Jyotirlinga, temple circuits and sacred city travel for families and senior citizens.",
    images: ["/images/ujjain-shipra-hero.png"],
    type: "website",
  },
  twitter: { card: "summary_large_image" },
};

const travelSchema = {
  "@context": "https://schema.org",
  "@type": "TravelGuide",
  name: "IndianKumbh",
  description: "India’s practical pilgrimage travel guide for Kumbh Mela, Char Dham, 12 Jyotirlinga, temple circuits and sacred city travel.",
  about: ["Kumbh Mela", "Char Dham Yatra", "12 Jyotirlinga", "Temple Circuits", "Sacred Cities"].map((name) => ({ "@type": "TouristDestination", name })),
};

const gaMeasurementId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID || "G-HW223XXYK2";

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
        <Script src={`https://www.googletagmanager.com/gtag/js?id=${gaMeasurementId}`} strategy="afterInteractive" />
        <Script id="google-analytics" strategy="afterInteractive">{`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments)}gtag('js',new Date());gtag('config','${gaMeasurementId}');`}</Script>
      </body>
    </html>
  );
}
