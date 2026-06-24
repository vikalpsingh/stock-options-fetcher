import type { Metadata } from "next";
import { BadgeIndianRupee, CalendarCheck, MapPinned, ShieldCheck } from "lucide-react";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { PlanAndBook } from "@/components/plan-and-book";

export const metadata: Metadata = {
  title: "Plan and Book Ujjain Kumbh 2028 Trip | Travel and Stay Guide",
  description: "Plan your Ujjain Kumbh 2028 journey with route guidance, stay suggestions for Ujjain, Indore and Bhopal, and booking links.",
  keywords: ["plan Ujjain Kumbh trip", "Ujjain Kumbh hotel booking", "Ujjain travel booking", "Indore stay for Ujjain", "Ujjain Kumbh 2028 planner"],
  alternates: { canonical: "/plan-and-book" },
  openGraph: {
    title: "Plan & Book Your Ujjain Kumbh 2028 Trip",
    description: "Get a practical route and stay recommendation before comparing travel and hotel options.",
    images: ["/images/mahakal-ghat-temple.png"],
  },
};

export default function PlanAndBookPage() {
  const affiliateConfig = {
    travelBaseUrl: process.env.REDBUS_AFFILIATE_BASE_URL,
    hotelBaseUrl: process.env.BOOKING_AFFILIATE_BASE_URL,
  };

  return (
    <main>
      <Breadcrumbs items={[{ label: "Ujjain Kumbh 2028", href: "/ujjain-kumbh-2028" }, { label: "Plan & Book" }]} />
      <section className="brand-gradient temple-silhouette pattern-jaali px-4 py-16 text-white sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-xs font-bold uppercase tracking-[.18em] text-gold"><CalendarCheck className="h-4 w-4" />Ujjain 2028 planning MVP</p>
          <h1 className="mt-6 max-w-5xl text-balance font-serif text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">Plan &amp; Book Your Ujjain Kumbh 2028 Trip</h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/85 sm:text-xl">Find travel routes, stay options, and practical guidance for Ujjain, Indore, and Bhopal.</p>
          <div className="mt-8 grid max-w-4xl gap-3 sm:grid-cols-3">
            <TrustPoint icon={MapPinned} text="Rule-based route guidance" />
            <TrustPoint icon={BadgeIndianRupee} text="Budget-aware stay base" />
            <TrustPoint icon={ShieldCheck} text="No booking data collected" />
          </div>
        </div>
      </section>

      <section className="pattern-mandala bg-cream px-4 py-14 sm:px-6 lg:px-8 lg:py-20">
        <div className="mx-auto max-w-7xl">
          <PlanAndBook affiliateConfig={affiliateConfig} />
        </div>
      </section>
    </main>
  );
}

function TrustPoint({ icon: Icon, text }: { icon: React.ComponentType<{ className?: string }>; text: string }) {
  return <div className="flex items-center gap-3 rounded-2xl border border-white/15 bg-black/15 p-4 text-sm font-bold"><Icon className="h-5 w-5 shrink-0 text-gold" />{text}</div>;
}

