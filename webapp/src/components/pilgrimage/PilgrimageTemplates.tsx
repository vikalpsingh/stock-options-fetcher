import Link from "next/link";
import type { ComponentType } from "react";
import { AlertTriangle, ArrowRight, BedDouble, CalendarDays, HeartHandshake, Landmark, MapPin, PackageCheck, Route, ShieldCheck } from "lucide-react";
import { TravelSearchWidget } from "@/src/components/travel/TravelSearchWidget";
import { HotelBookingCTA } from "@/src/components/travel/HotelBookingCTA";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function PilgrimageHero({ eyebrow, title, subtitle, primaryHref = "/travel-tools", primaryLabel = "Plan travel", secondaryHref = "/packages", secondaryLabel = "Get package quote" }: { eyebrow: string; title: string; subtitle: string; primaryHref?: string; primaryLabel?: string; secondaryHref?: string; secondaryLabel?: string }) {
  return <section className="brand-gradient temple-silhouette pattern-mandala px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28"><div className="mx-auto max-w-7xl"><p className="inline-flex rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-xs font-black uppercase tracking-[.18em] text-gold">{eyebrow}</p><h1 className="mt-6 max-w-5xl font-serif text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">{title}</h1><p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/90 sm:text-xl">{subtitle}</p><div className="mt-8 flex flex-col gap-3 sm:flex-row"><Button asChild size="lg"><Link href={primaryHref}>{primaryLabel}<ArrowRight className="h-4 w-4" /></Link></Button><Button asChild variant="outline" size="lg"><Link href={secondaryHref}>{secondaryLabel}</Link></Button></div></div></section>;
}

export function SacredImportanceSection({ title = "Why this pilgrimage matters", text, points = [] }: { title?: string; text: string; points?: string[] }) {
  return <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[.85fr_1.15fr]"><SectionTitle eyebrow="Sacred importance" title={title} text={text} /><div className="grid gap-4 sm:grid-cols-2">{points.map((point) => <InfoCard key={point} icon={Landmark} title={point} text="Use this as a planning anchor; verify specific darshan rules and timings from official sources before travel." />)}</div></div></section>;
}

export function HowToReachSection({ title = "How to reach", text = "Compare train, flight, bus and hotel options using validated redirect links. Bookings are completed on partner websites." }: { title?: string; text?: string }) {
  return <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Travel planning" title={title} text={text} /><div className="mt-10"><TravelSearchWidget title="Search travel options" sourcePage="pilgrimage-template" /></div></div></section>;
}

export function BestTimeToVisitSection({ bestTime, duration }: { bestTime: string; duration: string }) {
  return <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto grid max-w-7xl gap-5 md:grid-cols-2"><InfoCard icon={CalendarDays} title="Best time to visit" text={bestTime} /><InfoCard icon={Route} title="Suggested duration" text={duration} /></div></section>;
}

export function ItineraryCards({ items }: { items: string[] }) {
  return <div className="grid gap-4 md:grid-cols-3">{items.map((item, index) => <Card key={item} className="border-gold/35"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">Plan {index + 1}</p><h3 className="mt-3 font-serif text-2xl">{item}</h3><p className="mt-3 text-sm leading-7 text-stone-600">Keep travel buffers, rest windows and official verification in the plan.</p></CardContent></Card>)}</div>;
}

export function SeniorCitizenTips({ difficulty = "moderate", notes = "Keep the itinerary slow, avoid peak heat, confirm lift/vehicle access and keep medicines, water and documents handy." }: { difficulty?: string; notes?: string }) {
  return <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><InfoCard icon={HeartHandshake} title={`Senior citizen suitability: ${difficulty}`} text={notes} /></div></section>;
}

export function StayRecommendation({ sourcePage = "pilgrimage-page" }: { sourcePage?: string }) {
  return <section className="bg-white px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><HotelBookingCTA title="Stay and hotel planning" sourcePage={sourcePage} /></div></section>;
}

export function TravelBookingWidget({ sourcePage = "pilgrimage-page" }: { sourcePage?: string }) {
  return <TravelSearchWidget title="Book travel on partner websites" sourcePage={sourcePage} />;
}

export function PackageCTA({ title = "Need assisted yatra planning?", text = "Request package support for family, senior citizen or group travel. Packages are fulfilled by independent travel partners.", href = "/packages" }: { title?: string; text?: string; href?: string }) {
  return <section className="bg-maroon px-4 py-12 text-white sm:px-6 lg:px-8"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-6 md:flex-row md:items-center"><div><p className="text-xs font-black uppercase tracking-[.2em] text-gold">Package support</p><h2 className="mt-2 font-serif text-3xl text-white">{title}</h2><p className="mt-3 max-w-2xl text-sm leading-7 text-orange-50/85">{text}</p></div><Button asChild size="lg"><Link href={href}><PackageCheck className="h-4 w-4" />Get package quote</Link></Button></div></section>;
}

export function FAQSection({ faqs }: { faqs: { question: string; answer: string }[] }) {
  const schema = { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faqs.map((faq) => ({ "@type": "Question", name: faq.question, acceptedAnswer: { "@type": "Answer", text: faq.answer } })) };
  return <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8"><div className="mx-auto max-w-4xl"><SectionTitle eyebrow="FAQs" title="Common planning questions" /><div className="mt-8 space-y-4">{faqs.map((faq) => <Card key={faq.question}><CardContent><h3 className="font-serif text-xl">{faq.question}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{faq.answer}</p></CardContent></Card>)}</div></div><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} /></section>;
}

export function OfficialDisclaimer() {
  return <div className="border-y border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-950 sm:px-6 lg:px-8"><div className="mx-auto flex max-w-7xl gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><p><strong>Official verification:</strong> Dates, temple timings, registrations, routes and official arrangements should be verified with government or temple authorities before travel.</p></div></div>;
}

export function SectionTitle({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return <div className="max-w-3xl"><p className="text-xs font-black uppercase tracking-[.2em] text-saffron">{eyebrow}</p><h2 className="mt-3 font-serif text-4xl font-semibold leading-tight text-ink sm:text-5xl">{title}</h2>{text && <p className="mt-4 text-lg leading-8 text-stone-600">{text}</p>}</div>;
}

function InfoCard({ icon: Icon, title, text }: { icon: ComponentType<{ className?: string }>; title: string; text: string }) {
  return <Card className="h-full border-gold/35 bg-[#fffdf8]"><CardContent><span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Icon className="h-6 w-6" /></span><h3 className="mt-5 font-serif text-2xl">{title}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{text}</p></CardContent></Card>;
}
