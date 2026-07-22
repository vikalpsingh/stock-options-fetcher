import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { ArrowRight, BedDouble, BusFront, HeartHandshake, Plane, ShieldCheck, TrainFront } from "lucide-react";
import type { KumbhGuide } from "@/src/data/kumbhGuides";
import { VerificationNote } from "@/src/components/common/VerificationNote";
import { LastKumbhStats } from "./LastKumbhStats";
import { KumbhPlacesGuide } from "./KumbhPlacesGuide";
import { KumbhTraditionsSection } from "./KumbhTraditionsSection";
import { TravelSearchWidget } from "@/src/components/travel/TravelSearchWidget";
import { HotelBookingCTA } from "@/src/components/travel/HotelBookingCTA";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function KumbhGuideLanding({ guide }: { guide: KumbhGuide }) {
  const isNashik = guide.slug === "nashik-kumbh-2027";
  const badge = guide.status === "current_focus" ? "Current Focus" : "Next Major Focus";
  const travelDefaults = travelDefaultsFor(guide.slug);
  const heroStyle: CSSProperties | undefined = isNashik
    ? {
        backgroundImage:
          "linear-gradient(90deg, rgba(52, 13, 18, 0.95), rgba(122, 39, 23, 0.84), rgba(65, 32, 14, 0.48)), url('/images/nashik-godavari-kumbh.jpg')",
        backgroundPosition: "center",
        backgroundSize: "cover",
      }
    : undefined;
  return (
    <main>
      <section style={heroStyle} className={`${isNashik ? "bg-maroon" : "brand-gradient"} temple-silhouette pattern-mandala px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28`}>
        <div className="mx-auto max-w-7xl">
          <p className="inline-flex rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-xs font-black uppercase tracking-[.18em] text-gold">{badge}: {guide.shortTitle}</p>
          <h1 className="mt-6 max-w-5xl font-serif text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">{guide.heroTitle}</h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/90 sm:text-xl">{guide.heroSubtitle}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row"><Button asChild size="lg"><Link href="#travel-options">Search hotel, bus, train and flight options<ArrowRight className="h-4 w-4" /></Link></Button><Button asChild variant="outline" size="lg"><Link href={`/kumbh-mela/${guide.slug}/places`}>See important places</Link></Button></div>
        </div>
      </section>
      <section className="bg-cream px-4 py-8 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><VerificationNote sourceId={isNashik ? "nashik-kumbh-editorial" : "ujjain-kumbh-editorial"} /></div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Quick facts" title="Start with the essentials" /><div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">{quickFacts(guide).map(([label, value]) => <Card key={label} className="border-gold/35"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{label}</p><p className="mt-2 font-serif text-2xl">{value}</p></CardContent></Card>)}</div></div></section>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Why it matters" title={`Why ${guide.shortTitle} matters`} /><div className="mt-8 grid gap-5 md:grid-cols-3">{guide.spiritualSignificance.map((item) => <InfoCard key={item} title={item} text="Use this as a planning anchor, then verify official arrangements before booking." />)}</div></div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="History and mythology" title="Story, tradition and timeline" /><div className="mt-8 grid gap-5 lg:grid-cols-[.8fr_1.2fr]"><div className="space-y-4">{guide.mythologyStories.map((story) => <InfoCard key={story.title} title={story.title} text={story.summary} />)}</div><div className="space-y-4">{guide.historicalTimeline.map((item) => <Card key={item.period} className="border-gold/35"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{item.period}</p><h3 className="mt-2 font-serif text-2xl">{item.title}</h3><p className="mt-2 text-sm leading-7 text-stone-600">{item.description}</p></CardContent></Card>)}</div></div></div></section>
      <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Previous Kumbh" title="Last Kumbh highlights and traveller learnings" /><div className="mt-8"><LastKumbhStats destinationSlug={guide.slug} previousEventYear={guide.lastKumbhStats.previousEventYear} estimatedVisitors={guide.lastKumbhStats.estimatedPilgrims} duration={guide.lastKumbhStats.duration} infrastructureBudget={guide.lastKumbhStats.infrastructureNotes} keyLearnings={[guide.lastKumbhStats.infrastructureNotes, guide.lastKumbhStats.crowdNotes]} travellerTakeaways={guide.travellerWarnings} sourceNote={guide.lastKumbhStats.sourceNote} confidenceLevel={guide.lastKumbhStats.confidenceLevel} /></div></div></section>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Places" title="Important places, temples and bathing locations" /><div className="mt-8"><KumbhPlacesGuide guide={guide} /></div></div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="How to reach" title={`How to reach ${guide.city}`} /><div className="mt-8 grid gap-5 md:grid-cols-4">{["Flight", "Train", "Bus", "Road"].map((mode) => <InfoCard key={mode} title={mode} text={reachText(guide.slug, mode)} />)}</div></div></section>
      <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Stay" title="Where to stay" /><div className="mt-8 grid gap-5 md:grid-cols-3">{stayOptions(guide.slug).map((item) => <InfoCard key={item.title} title={item.title} text={item.text} />)}</div></div></section>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Useful services" title="Services travellers should look for" /><div className="mt-8 grid gap-4 md:grid-cols-3">{[...guide.usefulServices].sort((a, b) => a.priority - b.priority).map((service) => <InfoCard key={service.title} title={service.title} text={service.description} />)}</div></div></section>
      <KumbhTraditionsSection guide={guide} />
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-2"><TipList title="Senior citizen tips" icon={<HeartHandshake className="h-6 w-6 text-saffron" />} items={guide.seniorCitizenTips} /><TipList title="Family travel tips" icon={<ShieldCheck className="h-6 w-6 text-saffron" />} items={guide.familyTips} /></div></section>
      <section id="travel-options" className="scroll-mt-24 bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Travel widgets" title="Search hotel, bus, train and flight options" /><div className="mt-8"><TravelSearchWidget title={`Plan travel for ${guide.shortTitle}`} sourcePage={`kumbh-${guide.slug}`} campaign={guide.slug} {...travelDefaults} /></div><div className="mt-8"><HotelBookingCTA title={`Hotel options for ${guide.shortTitle}`} sourcePage={`kumbh-${guide.slug}`} campaign={guide.slug} /></div></div></section>
      <KumbhFAQ guide={guide} />
      <KumbhSchemas guide={guide} pageType="landing" />
    </main>
  );
}

export function SectionTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <div className="max-w-3xl"><p className="text-xs font-black uppercase tracking-[.2em] text-saffron">{eyebrow}</p><h2 className="mt-3 font-serif text-4xl font-semibold leading-tight text-ink sm:text-5xl">{title}</h2></div>;
}

export function InfoCard({ title, text }: { title: string; text: string }) {
  return <Card className="h-full border-gold/35 bg-[#fffdf8]"><CardContent><h3 className="font-serif text-2xl">{title}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{text}</p></CardContent></Card>;
}

export function TipList({ title, items, icon }: { title: string; items: string[]; icon: ReactNode }) {
  return <Card className="border-gold/35"><CardContent><div className="flex items-center gap-3">{icon}<h3 className="font-serif text-3xl">{title}</h3></div><ul className="mt-5 space-y-3 text-sm leading-7 text-stone-600">{items.map((item) => <li key={item}>• {item}</li>)}</ul></CardContent></Card>;
}

export function KumbhFAQ({ guide }: { guide: KumbhGuide }) {
  const faqs = guide.slug.includes("nashik") ? nashikFaqs : ujjainFaqs;
  return <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-5xl"><SectionTitle eyebrow="FAQs" title={`${guide.shortTitle} FAQs`} /><div className="mt-8 space-y-4">{faqs.map((faq) => <Card key={faq.question} className="border-gold/35"><CardContent><h3 className="font-serif text-xl">{faq.question}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{faq.answer}</p></CardContent></Card>)}</div></div></section>;
}

export function KumbhSchemas({ guide, pageType }: { guide: KumbhGuide; pageType: "landing" | "history" }) {
  const faqs = guide.slug.includes("nashik") ? nashikFaqs : ujjainFaqs;
  const faqSchema = { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faqs.map((faq) => ({ "@type": "Question", name: faq.question, acceptedAnswer: { "@type": "Answer", text: faq.answer } })) };
  const breadcrumbSchema = { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: "Home", item: "https://indiankumbh.com/" }, { "@type": "ListItem", position: 2, name: "Kumbh Mela", item: "https://indiankumbh.com/kumbh-mela" }, { "@type": "ListItem", position: 3, name: guide.title, item: `https://indiankumbh.com/kumbh-mela/${guide.slug}` }] };
  const articleSchema = pageType === "history" ? { "@context": "https://schema.org", "@type": "Article", headline: `${guide.shortTitle} history and story`, about: guide.title } : null;
  return <><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} /><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbSchema) }} />{articleSchema && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(articleSchema) }} />}</>;
}

function quickFacts(guide: KumbhGuide): [string, string][] {
  const hubs = guide.slug.includes("nashik") ? "Nashik, Trimbakeshwar, Shirdi, Mumbai, Pune" : "Ujjain, Indore, Bhopal";
  const bathing = guide.slug.includes("nashik") ? "Ramkund and Kushavarta Kund" : "Ram Ghat and Shipra river ghats";
  return [["City", guide.city], ["State", guide.state], ["Sacred river", guide.river], ["Main temple", guide.associatedTemple], ["Key bathing areas", bathing], ["Best nearby hubs", hubs]];
}

function reachText(slug: string, mode: string) {
  if (slug.includes("nashik")) {
    return { Flight: "Use Nashik where available; Mumbai and Pune are stronger arrival hubs.", Train: "Nashik Road is the key rail station.", Bus: "Useful from Mumbai, Pune, Shirdi, Aurangabad, Surat and Ahmedabad.", Road: "Mumbai–Pune–Nashik corridor is important; verify traffic controls." }[mode]!;
  }
  return { Flight: "Indore airport is the main practical airport.", Train: "Ujjain Junction is the key station.", Bus: "Useful from Indore, Bhopal, Ahmedabad, Mumbai, Pune and Delhi.", Road: "Indore–Ujjain corridor is important; verify traffic controls." }[mode]!;
}

function stayOptions(slug: string) {
  return slug.includes("nashik")
    ? [{ title: "Nashik city", text: "Best for families, hotels, city access and Ramkund." }, { title: "Trimbakeshwar", text: "Best for Jyotirlinga darshan and Kushavarta Kund." }, { title: "Shirdi", text: "Best for combined Sai Baba + Trimbakeshwar trips." }, { title: "Mumbai/Pune", text: "Arrival/departure hubs, not daily Kumbh stay bases." }]
    : [{ title: "Ujjain", text: "Best for Mahakal darshan, Shipra snan and short stays." }, { title: "Indore", text: "Best for airport, better hotels and family comfort." }, { title: "Bhopal", text: "Best for extended MP trip and Sanchi/Bhojpur add-ons." }];
}

function travelDefaultsFor(slug: string) {
  return slug.includes("nashik")
    ? { defaultFromCity: "pune", defaultToCity: "nashik", defaultHotelCity: "nashik", defaultFlightToCity: "nashik", packageHref: "/kumbh-mela/nashik-kumbh-2027/packages" }
    : { defaultFromCity: "bengaluru", defaultToCity: "ujjain", defaultHotelCity: "ujjain", defaultFlightToCity: "ujjain", packageHref: "/kumbh-mela/ujjain-kumbh-2028/packages" };
}

export const nashikFaqs = [
  ["What is Nashik-Trimbakeshwar Kumbh?", "It is the Kumbh associated with Nashik, Trimbakeshwar, the Godavari river and Trimbakeshwar Jyotirlinga."],
  ["When is Nashik Kumbh 2027?", "It is expected around the 2027 cycle, but official dates and bathing days should be verified from authorities."],
  ["Where does Nashik Kumbh happen?", "Planning usually involves Nashik city areas such as Ramkund and Trimbakeshwar/Kushavarta Kund as a separate zone."],
  ["What is the difference between Nashik and Trimbakeshwar locations?", "Nashik city and Trimbakeshwar are separate movement zones with different crowd patterns and stay needs."],
  ["What is Ramkund?", "Ramkund is an important Godavari ghat in Nashik."],
  ["What is Kushavarta Kund?", "Kushavarta Kund is a sacred kund at Trimbakeshwar linked with Godavari origin traditions."],
  ["Is Trimbakeshwar Jyotirlinga near Nashik?", "Yes, it is near Nashik and should usually be planned as a separate half-day or full-day movement."],
  ["Should I stay in Nashik or Trimbakeshwar?", "Nashik suits families and hotels; Trimbakeshwar suits Jyotirlinga focus but may have limited options."],
  ["Can I combine Nashik Kumbh with Shirdi?", "Yes, Shirdi is a practical nearby pilgrimage add-on if you keep enough travel buffer."],
  ["Is Nashik Kumbh suitable for senior citizens?", "Yes, with slow pacing, accessible stay, verified transport and avoidance of peak crowd rush."],
  ["Which airport is best for Nashik Kumbh?", "Nashik may work where flights are available; Mumbai and Pune are stronger fallback hubs."],
  ["Are official dates and bathing days final?", "Treat dates as to be confirmed until official announcements are published."],
].map(([question, answer]) => ({ question, answer }));

export const ujjainFaqs = [
  ["What is Ujjain Simhastha Kumbh?", "It is the Kumbh held in Ujjain around the Shipra river and Mahakaleshwar Jyotirlinga tradition."],
  ["When is Ujjain Kumbh 2028?", "It is expected for the 2028 cycle, but final dates and bathing days should be verified officially."],
  ["Where does Ujjain Kumbh happen?", "It centres around Ujjain, Shipra river ghats, Ram Ghat and related pilgrimage zones."],
  ["What is the importance of Shipra river?", "Shipra is the sacred river associated with Ujjain Simhastha snan."],
  ["Is Mahakaleshwar Jyotirlinga part of Ujjain Kumbh travel?", "Yes, Mahakal darshan is a major anchor, but peak-day planning must be careful."],
  ["Should I stay in Ujjain or Indore?", "Stay in Ujjain for darshan proximity; choose Indore for airport access and broader hotels."],
  ["Can I combine Ujjain with Omkareshwar?", "Yes, but plan Omkareshwar as a separate day or overnight extension."],
  ["Is Ujjain Kumbh suitable for senior citizens?", "Yes, with slower pacing, rest windows and avoiding packed peak-day combinations."],
  ["Which airport is best for Ujjain Kumbh?", "Indore airport is usually the practical airport for Ujjain."],
  ["Are official dates and bathing days final?", "Treat all dates as tentative until official confirmation."],
].map(([question, answer]) => ({ question, answer }));
