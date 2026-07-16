import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms",
  description: "Basic terms for using IndianKumbh.com travel planning information and partner links.",
  alternates: { canonical: "/terms" },
};

export default function TermsPage() {
  return (
    <main className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-4xl rounded-[2rem] border border-gold/35 bg-white p-6 shadow-soft sm:p-10">
        <h1 className="font-serif text-4xl font-semibold text-ink sm:text-5xl">Terms</h1>
        <div className="mt-6 space-y-5 leading-8 text-stone-600">
          <p>IndianKumbh.com provides general travel planning information for Kumbh Mela destinations. It is not a government website and does not replace official announcements.</p>
          <p>Dates, routes, crowd controls, darshan rules, bathing schedules, prices and availability can change. Travellers should verify important details with official authorities and travel partners before booking or travelling.</p>
          <p>Use of partner links may redirect you to third-party websites. Their terms, privacy practices, payment process and customer support apply to bookings completed there.</p>
        </div>
      </div>
    </main>
  );
}
