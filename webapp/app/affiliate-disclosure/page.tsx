import type { Metadata } from "next";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";

export const metadata: Metadata = {
  title: "Affiliate Disclosure",
  description: "Affiliate and referral disclosure for IndianKumbh.com hotel, travel, tour and package links.",
  alternates: { canonical: "/affiliate-disclosure" },
};

export default function AffiliateDisclosurePage() {
  return (
    <main className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-4xl rounded-[2rem] border border-gold/35 bg-white p-6 shadow-soft sm:p-10">
        <ShieldCheck className="h-10 w-10 text-saffron" />
        <h1 className="mt-5 font-serif text-4xl font-semibold text-ink sm:text-5xl">Affiliate Disclosure</h1>
        <p className="mt-6 text-lg leading-8 text-stone-700">IndianKumbh.com may earn a referral or affiliate commission when users click booking links for buses, hotels, flights, trains, tours or packages. This does not increase the price paid by the user. Bookings are completed on partner websites.</p>
        <p className="mt-5 leading-8 text-stone-600">Hotel bookings are completed on the travel partner website, such as Booking.com. Prices, availability, cancellation, refund and service terms are controlled by the travel partner.</p>
        <p className="mt-5 leading-8 text-stone-600">IndianKumbh.com helps travellers discover options and plan responsibly. We do not collect hotel payments, confirm hotel bookings, operate hotels or control partner inventory.</p>
        <p className="mt-8 text-sm text-stone-500">Also read our <Link href="/travel-partner-disclaimer" className="font-bold text-maroon underline">Travel Partner Disclaimer</Link> and <Link href="/privacy" className="font-bold text-maroon underline">Privacy Policy</Link>.</p>
      </div>
    </main>
  );
}
