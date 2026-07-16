import type { Metadata } from "next";
import { AlertTriangle } from "lucide-react";

export const metadata: Metadata = {
  title: "Travel Partner Disclaimer",
  description: "Important limitations for partner hotel, travel, tour and package links on IndianKumbh.com.",
  alternates: { canonical: "/travel-partner-disclaimer" },
};

export default function TravelPartnerDisclaimerPage() {
  return (
    <main className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-4xl rounded-[2rem] border border-gold/35 bg-white p-6 shadow-soft sm:p-10">
        <AlertTriangle className="h-10 w-10 text-saffron" />
        <h1 className="mt-5 font-serif text-4xl font-semibold text-ink sm:text-5xl">Travel Partner Disclaimer</h1>
        <div className="mt-6 space-y-5 leading-8 text-stone-600">
          <p>IndianKumbh.com is a travel discovery and planning website. Independent partners may provide hotel booking, buses, flights, tours, taxis, package quotes or other travel services.</p>
          <p>IndianKumbh.com does not operate hotels, buses, flights, tours or pilgrimage packages directly. Final booking, payment, cancellation, refund, taxes, inclusions and service delivery are controlled by the travel partner or supplier.</p>
          <p>Before paying any partner, travellers should verify price, room category, distance, transport pickup point, senior citizen support, cancellation terms and official Kumbh or temple arrangements in writing.</p>
        </div>
      </div>
    </main>
  );
}
