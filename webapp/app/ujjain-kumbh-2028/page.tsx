import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BedDouble,
  BusFront,
  CalendarDays,
  Clock3,
  Landmark,
  MapPinned,
  Route,
  ShieldCheck,
  Soup,
  Sparkles,
  Users,
} from "lucide-react";
import { FAQAccordion } from "@/components/faq-accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { getKumbhSite } from "@/src/data/kumbhSites";

const ujjain = getKumbhSite("ujjain-kumbh-2028")!;

export const metadata: Metadata = {
  title: "Ujjain Simhastha Kumbh 2028 Guide",
  description: "Plan Ujjain Simhastha 2028 with guidance for Shipra snan, Mahakaleshwar Jyotirlinga, stays, routes, food and family pilgrimage travel.",
  keywords: ["Ujjain Simhastha Kumbh 2028", "Mahakal darshan", "Shipra snan", "Ujjain family trip", "Ujjain Kumbh stay"],
  alternates: { canonical: "/ujjain-kumbh-2028" },
  openGraph: {
    title: "Ujjain Simhastha Kumbh 2028",
    description: "Family-focused pilgrimage guidance for Mahakal darshan, Shipra snan, stays, routes and Ujjain travel.",
    images: ["/images/mahakal-ghat-temple.png"],
  },
};

const planningCards = [
  { title: "Best place to stay", text: "Compare Ujjain, Indore and Bhopal for darshan access, airport convenience and family comfort.", href: "/stay", icon: BedDouble },
  { title: "How to reach Ujjain", text: "Plan flight, train and road approaches with realistic crowd and transfer buffers.", href: "/how-to-reach", icon: BusFront },
  { title: "Mahakal darshan", text: "Understand Bhasma Aarti preparation, temple rules and a comfortable sacred circuit.", href: "/mahakal-guide", icon: Landmark },
  { title: "Snan dates", text: "Track the planning calendar. Exact bathing dates remain tentative until officially announced.", href: "/kumbh-calendar", icon: CalendarDays },
  { title: "Crowd planning", text: "Prepare meeting points, walking buffers, family ID, hydration and flexible travel windows.", href: "/itineraries", icon: Users },
  { title: "Food and local transport", text: "Find light Malwa meals, safer food choices, Maps links and practical local movement guidance.", href: "/food-guide", icon: Soup },
];

const tripTypes = [
  { title: "1 day darshan", meta: "Focused pilgrimage", text: "Mahakal darshan, one nearby temple, a proper rest break and Ram Ghat or Mahakal Lok.", href: "/itineraries", icon: Clock3 },
  { title: "2 day family trip", meta: "Balanced family pace", text: "Use the first day for arrival and orientation, then keep a flexible second day for darshan and temples.", href: "/plan-my-trip", icon: Users },
  { title: "3 day Ujjain + Omkareshwar", meta: "Two Jyotirlingas", text: "Give Ujjain enough time, then reserve a separate early-start day for Omkareshwar.", href: "/nearby-destinations", icon: MapPinned },
  { title: "Indore base plan", meta: "Airport and hotel comfort", text: "Stay in Indore for wider hotels and food while planning an early, buffered transfer to Ujjain.", href: "/stay", icon: Route },
];

const faqs = [
  { question: "When will the official Ujjain Simhastha 2028 dates be confirmed?", answer: "The current planning window is tentative. Treat dates, bathing schedules, traffic plans and local arrangements as unconfirmed until Madhya Pradesh government and official district or temple authorities publish them." },
  { question: "How many days should a family keep for Ujjain?", answer: "Two full days are a practical minimum for Mahakal darshan and selected Ujjain sites. During Simhastha, three or more nights provide a safer buffer for crowds, route changes and rest." },
  { question: "Should we stay in Ujjain or Indore?", answer: "Choose Ujjain for easier early darshan and less daily travel. Choose Indore for airport access, broader hotel choice and food, while allowing an early transfer and festival traffic buffer." },
  { question: "Can elderly parents comfortably visit Mahakal and the Shipra ghats?", answer: "Yes, with a slower plan: early travel, fewer stops, water and medicines, rest after darshan and current assisted-access guidance verified from official sources." },
  { question: "Can Omkareshwar be added to the Ujjain trip?", answer: "Yes. It is better planned as a separate full day or overnight extension rather than added after a demanding Mahakal darshan day." },
];

export default function UjjainKumbhPage() {
  const faqSchema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };

  return (
    <main>
      <section className="temple-silhouette relative min-h-[680px] overflow-hidden bg-maroon text-white">
        <Image src="/images/mahakal-ghat-temple.png" alt={ujjain.imageAlt} fill priority className="object-cover object-[62%_center]" sizes="100vw" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#19080a]/95 via-[#50171b]/82 to-[#641f26]/25" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#260d0f]/85 via-transparent to-black/15" />
        <div className="pattern-mandala absolute inset-0 opacity-10" />
        <div className="relative mx-auto flex min-h-[680px] max-w-7xl items-center px-4 py-20 sm:px-6 lg:px-8">
          <div className="max-w-4xl">
            <p className="inline-flex items-center gap-2 rounded-full border border-gold/40 bg-black/20 px-4 py-2 text-xs font-bold uppercase tracking-[.18em] text-gold"><Sparkles className="h-4 w-4" />IndianKumbh featured guide</p>
            <h1 className="mt-6 text-balance font-serif text-5xl font-semibold leading-[1.04] sm:text-6xl lg:text-7xl">Ujjain Simhastha Kumbh 2028</h1>
            <p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/90 sm:text-xl">Plan a meaningful pilgrimage around the Shipra River and Mahakaleshwar Jyotirlinga, with practical family travel guidance for darshan, stays, routes, food and nearby journeys.</p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row"><Button asChild size="lg"><Link href="/plan-my-trip">Plan My Ujjain Trip<ArrowRight className="h-4 w-4" /></Link></Button><Button asChild variant="outline" size="lg"><Link href="/mahakal-guide">Explore Mahakal Guide</Link></Button></div>
          </div>
        </div>
      </section>

      <section className="border-b border-amber-200 bg-amber-50 px-4 py-5 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl gap-3 text-sm leading-6 text-amber-950"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><p><strong>Important notice:</strong> {ujjain.tentativeDates} Dates, snan schedules, routes and official arrangements must be verified with government and official sources before travel.</p></div>
      </section>

      <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Quick planning" title="Start with the decision your family needs to make" text="Each guide answers one practical question and links directly to the deeper Ujjain planning page." />
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {planningCards.map(({ icon: Icon, ...card }) => <Link key={card.href} href={card.href} className="group"><Card className="premium-card h-full border-gold/30 transition group-hover:-translate-y-1 group-hover:border-saffron/50"><CardContent><span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Icon className="h-6 w-6" /></span><h2 className="mt-5 font-serif text-2xl">{card.title}</h2><p className="mt-3 text-sm leading-7 text-stone-600">{card.text}</p><span className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-maroon">Open guide<ArrowRight className="h-4 w-4" /></span></CardContent></Card></Link>)}
          </div>
        </div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Suggested trip types" title="Choose a pace that protects the pilgrimage" text="Shorter plans should remain focused. Longer plans can add Omkareshwar, Indore and more rest." />
          <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            {tripTypes.map(({ icon: Icon, ...trip }) => <Card key={trip.title} className="h-full overflow-hidden border-gold/30"><div className="brand-gradient pattern-jaali p-6 text-white"><Icon className="h-7 w-7 text-gold" /><p className="mt-6 text-xs font-bold uppercase tracking-wider text-orange-100">{trip.meta}</p><h2 className="mt-2 font-serif text-2xl text-white">{trip.title}</h2></div><CardContent><p className="text-sm leading-7 text-stone-600">{trip.text}</p><Button asChild variant="outline" className="mt-6 w-full"><Link href={trip.href}>Use this plan<ArrowRight className="h-4 w-4" /></Link></Button></CardContent></Card>)}
          </div>
        </div>
      </section>

      <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <SectionHeading eyebrow="Continue planning" title="Go directly to the detailed Ujjain guides" />
          <div className="mt-8 flex flex-wrap gap-3">
            {[["Mahakal Guide", "/mahakal-guide"], ["Stay Guide", "/stay"], ["Plan My Trip", "/plan-my-trip"], ["Nearby Destinations", "/nearby-destinations"], ["Itineraries", "/itineraries"], ["Food Guide", "/food-guide"]].map(([label, href]) => <Button key={href} asChild variant="outline"><Link href={href}>{label}<ArrowRight className="h-4 w-4" /></Link></Button>)}
          </div>
        </div>
      </section>

      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[.7fr_1.3fr]">
          <SectionHeading eyebrow="Ujjain 2028 FAQs" title="Answers for safer early planning" text="Official arrangements can change as Simhastha preparations develop." />
          <FAQAccordion items={faqs} />
        </div>
      </section>

      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-6 rounded-[2rem] bg-maroon p-8 text-center text-white sm:p-12 md:flex-row md:text-left">
          <div><p className="text-xs font-bold uppercase tracking-[.2em] text-gold">Build a practical pilgrimage</p><h2 className="mt-2 font-serif text-3xl">Ready to plan your Ujjain Kumbh journey?</h2></div>
          <Button asChild size="lg"><Link href="/plan-my-trip">Plan My Trip<ArrowRight className="h-4 w-4" /></Link></Button>
        </div>
      </section>

      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />
    </main>
  );
}

function SectionHeading({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return <div className="max-w-3xl"><p className="text-xs font-bold uppercase tracking-[.2em] text-saffron">{eyebrow}</p><h2 className="mt-3 font-serif text-4xl font-semibold leading-tight text-ink sm:text-5xl">{title}</h2>{text && <p className="mt-4 text-lg leading-8 text-stone-600">{text}</p>}</div>;
}
