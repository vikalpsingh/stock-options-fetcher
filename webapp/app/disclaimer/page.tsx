import type { Metadata } from "next";
import { AlertTriangle, Mail } from "lucide-react";

export const metadata: Metadata = {
  title: "Travel and Package Disclaimer",
  description: "Important limitations for IndianKumbh.com travel guidance, package enquiries and affiliate links.",
  alternates: { canonical: "/disclaimer" },
};

export default function DisclaimerPage() {
  return (
    <main className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-4xl">
        <p className="text-xs font-black uppercase tracking-[.2em] text-saffron">Before you travel or book</p>
        <h1 className="mt-3 font-serif text-5xl font-semibold sm:text-6xl">Travel and Package Disclaimer</h1>
        <div className="mt-8 flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><p>Dates, snan schedules, routes, darshan rules, traffic plans and local arrangements must be verified with government, temple and other official sources before travel.</p></div>
        <div className="mt-10 space-y-5">
          <Disclaimer title="Independent information platform">IndianKumbh.com provides travel information, planning tools, package discovery and referral services. We are not a government authority, temple authority, railway, airline, hotel, tour operator or travel insurer.</Disclaimer>
          <Disclaimer title="Independent travel partners">Packages are fulfilled by independent travel partners. The partner is responsible for the final itinerary, price, taxes, availability, service delivery, payment, cancellation, refund, customer support and any promised assistance.</Disclaimer>
          <Disclaimer title="Indicative information">Package descriptions and price labels are planning aids and are not binding offers. Obtain a written quote and review all inclusions, exclusions and terms before payment.</Disclaimer>
          <Disclaimer title="Darshan and special access">IndianKumbh.com does not guarantee Mahakal darshan, Bhasma Aarti registration, snan access, queue priority or festival permissions. Avoid providers promising unauthorised access.</Disclaimer>
          <Disclaimer title="Affiliate links">We may earn a commission when you use selected hotel or travel links. This does not increase our control over the partner’s inventory, pricing, privacy practices or service quality.</Disclaimer>
          <Disclaimer title="Personal responsibility">Travellers should independently assess health, mobility, weather, crowd and safety requirements and obtain suitable medical advice and travel insurance where appropriate.</Disclaimer>
        </div>
        <p className="mt-8 flex items-center gap-2 text-sm font-semibold text-stone-700"><Mail className="h-4 w-4 text-saffron" />Questions: info@indiankumbh.com</p>
      </div>
    </main>
  );
}

function Disclaimer({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="rounded-3xl border border-gold/30 bg-white p-6 sm:p-8"><h2 className="font-serif text-2xl">{title}</h2><p className="mt-3 leading-7 text-stone-600">{children}</p></section>;
}
