import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, BedDouble, BusFront, Car, HeartHandshake, Plane, ShieldCheck, TrainFront } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { VerificationNote } from "@/src/components/common/VerificationNote";
import { KumbhPlacesGuide } from "@/src/components/kumbh/KumbhPlacesGuide";
import { KumbhTraditionsSection } from "@/src/components/kumbh/KumbhTraditionsSection";
import { KumbhFAQ, KumbhSchemas, SectionTitle, InfoCard, nashikFaqs, ujjainFaqs } from "@/src/components/kumbh/KumbhGuidePage";
import { TravelSearchWidget } from "@/src/components/travel/TravelSearchWidget";
import { HotelBookingCTA } from "@/src/components/travel/HotelBookingCTA";
import { PackageLeadForm } from "@/src/components/packages/PackageLeadForm";
import { getKumbhGuide, kumbhGuides, type KumbhGuide } from "@/src/data/kumbhGuides";

const sections = ["history", "places", "how-to-reach", "stay", "services", "packages", "faqs"] as const;
type SectionSlug = (typeof sections)[number];

export function generateStaticParams() {
  return kumbhGuides.flatMap((guide) => sections.map((section) => ({ slug: guide.slug, section })));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string; section: string }> }): Promise<Metadata> {
  const { slug, section } = await params;
  const guide = getKumbhGuide(slug);
  if (!guide || !isSection(section)) return { title: "Kumbh Guide" };
  const label = sectionTitle(section);
  return {
    title: `${label} | ${guide.shortTitle} | IndianKumbh.com`,
    description: `${label} for ${guide.shortTitle}: practical guidance for families, senior citizens and pilgrimage travellers.`,
    keywords: guide.seoKeywords,
    alternates: { canonical: `/kumbh-mela/${slug}/${section}` },
  };
}

export default async function KumbhSectionPage({ params }: { params: Promise<{ slug: string; section: string }> }) {
  const { slug, section } = await params;
  const guide = getKumbhGuide(slug);
  if (!guide || !isSection(section)) notFound();
  return (
    <main>
      <SectionHero guide={guide} section={section} />
      {section === "history" && <HistoryStoriesPage guide={guide} />}
      {section === "places" && <PlacesPage guide={guide} />}
      {section === "how-to-reach" && <HowToReachPage guide={guide} />}
      {section === "stay" && <StayPage guide={guide} />}
      {section === "services" && <ServicesPage guide={guide} />}
      {section === "packages" && <PackagesPage guide={guide} />}
      {section === "faqs" && <><KumbhFAQ guide={guide} /><KumbhSchemas guide={guide} pageType="landing" /></>}
    </main>
  );
}

function SectionHero({ guide, section }: { guide: KumbhGuide; section: SectionSlug }) {
  return (
    <section className="brand-gradient temple-silhouette pattern-mandala px-4 py-16 text-white sm:px-6 lg:px-8 lg:py-24">
      <div className="mx-auto max-w-7xl">
        <p className="text-xs font-black uppercase tracking-[.2em] text-gold">{guide.shortTitle}</p>
        <h1 className="mt-4 max-w-4xl font-serif text-5xl font-semibold leading-tight text-white">{sectionTitle(section)}</h1>
        <p className="mt-5 max-w-3xl text-lg leading-8 text-orange-50/85">Practical, family-friendly and senior-aware planning for {guide.city}. Verify official dates, routes and services before booking travel.</p>
      </div>
    </section>
  );
}

function HistoryStoriesPage({ guide }: { guide: KumbhGuide }) {
  const isNashik = guide.slug.includes("nashik");
  const fourPlaces = [
    ["Haridwar", "Ganga"],
    ["Prayagraj", "Sangam"],
    ["Nashik", "Godavari"],
    ["Ujjain", "Shipra"],
  ];
  return (
    <>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <VerificationNote sourceId={isNashik ? "nashik-kumbh-editorial" : "ujjain-kumbh-editorial"} />
        <div className="mt-10 grid gap-6 lg:grid-cols-[.9fr_1.1fr]">
          <InfoCard title="What is Kumbh Mela?" text="Kumbh Mela is one of India's most important Hindu pilgrimage gatherings, centred on sacred rivers, holy bathing, akhara processions, pravachan, satsang and family pilgrimage." />
          <InfoCard title="Samudra Manthan and the Amrit Kalash" text="Traditional belief connects Kumbh with the churning of the ocean and drops of amrit. The story is presented respectfully as religious tradition and cultural memory." />
        </div>
      </div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="Why four places?" title="Sacred rivers of the Kumbh tradition" />
        <div className="mt-8 grid gap-4 md:grid-cols-4">{fourPlaces.map(([city, river]) => <InfoCard key={city} title={city} text={`${city} is associated with the sacred ${river} tradition in Kumbh travel.`} />)}</div>
      </div></section>
      <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="Destination story" title={isNashik ? "Godavari, Trimbakeshwar, Ramkund and Panchavati" : "Shipra, Mahakaleshwar, Simhastha and Ram Ghat"} />
        <div className="mt-8 grid gap-5 md:grid-cols-2">{guide.mythologyStories.map((story) => <InfoCard key={story.title} title={story.title} text={story.summary} />)}</div>
      </div></section>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="Timeline" title="Previous and upcoming Kumbh planning" />
        <div className="mt-8 space-y-4">{guide.historicalTimeline.map((item) => <Card key={item.period} className="border-gold/35"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{item.period}</p><h2 className="mt-2 font-serif text-2xl">{item.title}</h2><p className="mt-2 text-sm leading-7 text-stone-600">{item.description}</p></CardContent></Card>)}</div>
      </div></section>
      <KumbhTraditionsSection guide={guide} />
      <section className="bg-amber-50 px-4 py-8 text-sm leading-7 text-amber-950 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl">Historical and religious stories are presented as traditional beliefs. Official event arrangements and dates should be verified from authorities.</div></section>
      <KumbhSchemas guide={guide} pageType="history" />
    </>
  );
}

function PlacesPage({ guide }: { guide: KumbhGuide }) {
  return <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><KumbhPlacesGuide guide={guide} /></div></section>;
}

function HowToReachPage({ guide }: { guide: KumbhGuide }) {
  const routes = routeCards(guide.slug);
  return (
    <>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="Travel modes" title={`How to reach ${guide.city}`} />
        <div className="mt-8 grid gap-5 md:grid-cols-4">{travelModes(guide.slug).map(({ title, text, icon: Icon }) => <Card key={title} className="border-gold/35"><CardContent><Icon className="h-7 w-7 text-saffron" /><h2 className="mt-4 font-serif text-2xl">{title}</h2><p className="mt-3 text-sm leading-7 text-stone-600">{text}</p></CardContent></Card>)}</div>
      </div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="Route cards" title="Best ways to reach for families and groups" />
        <div className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-3">{routes.map((route) => <Card key={route.title} className="border-gold/35"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{route.label}</p><h2 className="mt-2 font-serif text-2xl">{route.title}</h2><p className="mt-3 text-sm leading-7 text-stone-600">{route.note}</p><Button asChild variant="outline" className="mt-5 w-full"><Link href={route.href}>Open travel search<ArrowRight className="h-4 w-4" /></Link></Button></CardContent></Card>)}</div>
        <div className="mt-10"><TravelSearchWidget title={`Search travel for ${guide.shortTitle}`} sourcePage={`${guide.slug}-how-to-reach`} /></div>
      </div></section>
    </>
  );
}

function StayPage({ guide }: { guide: KumbhGuide }) {
  const isNashik = guide.slug.includes("nashik");
  return (
    <>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="Stay comparison" title={isNashik ? "Nashik vs Trimbakeshwar vs Shirdi" : "Ujjain vs Indore vs Bhopal"} />
        <div className="mt-8 grid gap-5 md:grid-cols-3">{stayCards(guide.slug).map((item) => <InfoCard key={item.title} title={item.title} text={item.text} />)}</div>
      </div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><HotelBookingCTA title={`Check hotels for ${guide.shortTitle}`} sourcePage={`${guide.slug}-stay`} campaign={guide.slug} /></div></section>
    </>
  );
}

function ServicesPage({ guide }: { guide: KumbhGuide }) {
  const isNashik = guide.slug.includes("nashik");
  const serviceGroups = [
    ["Accommodation", "Hotels, dharamshala, tent/camp options, group stay and senior citizen friendly stay."],
    ["Transport", "Local buses, taxi/auto, railway station transfer, airport transfer, walking routes and park-and-ride placeholders."],
    ["Medical and emergency", "Medical camps, ambulance, first aid, senior citizen checklist and emergency contact placeholder."],
    ["Police and helpdesk", "Lost and found, child/senior citizen assistance, crowd instructions and official helpline placeholder."],
    ["Food and water", "Drinking water, langar/bhandara, local food and safe eating tips."],
    ["Toilets and sanitation", "Public toilet placeholders, hygiene tips and carry checklist."],
    ["Digital services", "Official app/website placeholders, QR maps, route alerts and WhatsApp alert placeholder."],
    ["Package and booking help", "Hotel links, bus links, train links, flight links and package quote support."],
  ];
  return (
    <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
      <VerificationNote sourceId={isNashik ? "nashik-kumbh-editorial" : "ujjain-kumbh-editorial"} />
      <div className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-4">{serviceGroups.map(([title, text]) => <InfoCard key={title} title={title} text={text} />)}</div>
      <Card className="mt-10 border-gold/35 bg-white"><CardContent><h2 className="font-serif text-3xl">Destination-specific planning note</h2><p className="mt-4 leading-8 text-stone-600">{isNashik ? "Nashik city and Trimbakeshwar are separate planning zones. Ramkund and Kushavarta Kund may need different movement planning. Shirdi can be combined as a nearby pilgrimage." : "Ujjain and Indore should be planned together for stay and flight arrival. Mahakal darshan and Shipra snan should be planned separately on peak days. Omkareshwar and Maheshwar are useful add-ons."}</p><p className="mt-4 rounded-2xl bg-amber-50 p-4 text-sm text-amber-950">Service locations, helplines and official arrangements will be updated when authorities publish details.</p></CardContent></Card>
    </div></section>
  );
}

function PackagesPage({ guide }: { guide: KumbhGuide }) {
  const isNashik = guide.slug.includes("nashik");
  const categories = packageCategoriesFor(guide.slug);
  return (
    <>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <VerificationNote sourceId={isNashik ? "nashik-kumbh-editorial" : "ujjain-kumbh-editorial"} />
        <div className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-4">{categories.map((category) => <Card key={category.slug} className="border-gold/35 bg-white"><CardContent><h2 className="font-serif text-2xl">{category.title}</h2><p className="mt-3 text-sm leading-7 text-stone-600">Can include stay, local transport, route planning and family/senior citizen support depending on partner availability.</p><Link className="mt-5 inline-flex text-sm font-bold text-maroon" href={`?packageType=${category.slug}`}>Select package</Link></CardContent></Card>)}</div>
      </div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[.75fr_1.25fr]"><div><SectionTitle eyebrow="Package support" title="What can be included" /><ul className="mt-6 space-y-3 text-sm leading-7 text-stone-600"><li>• Hotel, dharamshala or group stay support</li><li>• Local transport and station/airport transfers</li><li>• Darshan/snana-day movement guidance where available</li><li>• Senior citizen and group coordination support</li><li>• Usually excluded: personal expenses, official paid entries, insurance, cancellations and items not confirmed by the partner.</li></ul><p className="mt-6 rounded-2xl bg-amber-50 p-4 text-sm leading-6 text-amber-950">IndianKumbh.com does not operate tours directly. Packages are fulfilled by independent travel partners. Final price, availability, inclusions, cancellation and refund terms are confirmed by the partner.</p></div><PackageLeadForm packageCategories={categories} destination={guide.title} /></div></section>
      <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><TravelSearchWidget title="Prefer self-booking travel?" sourcePage={`${guide.slug}-packages`} /></div></section>
    </>
  );
}

function isSection(value: string): value is SectionSlug {
  return sections.includes(value as SectionSlug);
}

function sectionTitle(section: SectionSlug) {
  return ({ history: "History and Story", places: "Important Places", "how-to-reach": "How to Reach", stay: "Where to Stay", services: "Useful Services", packages: "Packages and Assisted Yatra", faqs: "Frequently Asked Questions" } satisfies Record<SectionSlug, string>)[section];
}

function travelModes(slug: string) {
  const nashik = slug.includes("nashik");
  return [
    { title: "By flight", icon: Plane, text: nashik ? "Use Nashik where available; Mumbai and Pune are strong arrival hubs." : "Indore airport is usually the most practical airport for Ujjain." },
    { title: "By train", icon: TrainFront, text: nashik ? "Nashik Road railway station is the key rail point." : "Ujjain Junction is the key rail point for the Kumbh city." },
    { title: "By bus", icon: BusFront, text: nashik ? "Useful from Mumbai, Pune, Shirdi, Aurangabad, Surat and Ahmedabad." : "Useful from Indore, Bhopal, Ahmedabad, Mumbai, Pune and Delhi." },
    { title: "By road", icon: Car, text: nashik ? "Mumbai-Pune-Nashik corridor is important; verify event traffic rules." : "Indore-Ujjain corridor is important; verify event traffic rules." },
  ];
}

function routeCards(slug: string) {
  if (slug.includes("nashik")) {
    return [
      route("Mumbai to Nashik", "Best for family", "/go/travel?mode=train&from=mumbai&to=nashik&date=2027-08-01&campaign=nashik-kumbh-2027", "Train/road options; keep buffer during Kumbh period."),
      route("Pune to Nashik", "Best short trip", "/go/travel?mode=bus&from=pune&to=nashik&date=2027-08-01&campaign=nashik-kumbh-2027", "Road/bus route is popular; check traffic diversions."),
      route("Bengaluru to Nashik", "Best by flight", "/go/travel?mode=flight&from=bengaluru&to=nashik&departureDate=2027-08-01&campaign=nashik-kumbh-2027", "Consider Mumbai/Pune fallback if direct flight options are limited."),
      route("Ahmedabad to Nashik", "Best budget option", "/go/travel?mode=train&from=ahmedabad&to=nashik&date=2027-08-01&campaign=nashik-kumbh-2027", "Train or bus with early booking."),
      route("Delhi to Nashik", "Best for senior citizens", "/go/travel?mode=flight&from=delhi&to=nashik&departureDate=2027-08-01&campaign=nashik-kumbh-2027", "Prefer flight plus comfortable hotel base."),
      route("Shirdi to Nashik", "Pilgrimage add-on", "/go/travel?mode=bus&from=shirdi&to=nashik&date=2027-08-01&campaign=nashik-kumbh-2027", "Good for Sai Baba + Trimbakeshwar plans; verify city mapping before booking."),
    ];
  }
  return [
    route("Indore to Ujjain", "Best for family", "/go/travel?mode=bus&from=indore&to=ujjain&date=2028-04-01&campaign=ujjain-kumbh-2028", "Most practical arrival/stay combination."),
    route("Bhopal to Ujjain", "Extended MP trip", "/go/travel?mode=train&from=bhopal&to=ujjain&date=2028-04-01&campaign=ujjain-kumbh-2028", "Good for Sanchi/Bhojpur add-ons."),
    route("Bengaluru to Ujjain", "Best by flight", "/go/travel?mode=flight&from=bengaluru&to=indore&departureDate=2028-04-01&campaign=ujjain-kumbh-2028", "Fly to Indore, then travel to Ujjain."),
    route("Mumbai to Ujjain", "Best budget option", "/go/travel?mode=train&from=mumbai&to=ujjain&date=2028-04-01&campaign=ujjain-kumbh-2028", "Train route with early booking."),
    route("Pune to Ujjain", "Family option", "/go/travel?mode=train&from=pune&to=ujjain&date=2028-04-01&campaign=ujjain-kumbh-2028", "Train/road options; keep buffer."),
    route("Ahmedabad to Ujjain", "Best short trip", "/go/travel?mode=bus&from=ahmedabad&to=ujjain&date=2028-04-01&campaign=ujjain-kumbh-2028", "Bus or train based on comfort and timing."),
    route("Delhi to Ujjain", "Best for senior citizens", "/go/travel?mode=flight&from=delhi&to=indore&departureDate=2028-04-01&campaign=ujjain-kumbh-2028", "Prefer Indore flight plus comfortable stay."),
  ];
}

function route(title: string, label: string, href: string, note: string) {
  return { title, label, href, note };
}

function stayCards(slug: string) {
  return slug.includes("nashik")
    ? [
      { title: "Nashik city", text: "Best for families, hotels, city access and Ramkund." },
      { title: "Trimbakeshwar", text: "Best for Jyotirlinga darshan, Kushavarta Kund and focused spiritual stay." },
      { title: "Shirdi", text: "Best for Sai Baba + Trimbakeshwar package plans." },
      { title: "Mumbai/Pune", text: "Arrival/departure hubs, not recommended as daily Kumbh stay bases." },
    ]
    : [
      { title: "Ujjain", text: "Best for Mahakal darshan, Shipra snan and short stay." },
      { title: "Indore", text: "Best for airport, better hotels and family comfort." },
      { title: "Bhopal", text: "Best for extended MP trip, Sanchi/Bhojpur add-ons and slower itineraries." },
    ];
}

function packageCategoriesFor(slug: string) {
  return slug.includes("nashik")
    ? [
      { slug: "nashik-kumbh-trimbakeshwar-darshan", title: "Nashik Kumbh + Trimbakeshwar Darshan" },
      { slug: "nashik-kumbh-shirdi-package", title: "Nashik Kumbh + Shirdi Package" },
      { slug: "mumbai-to-nashik-kumbh-package", title: "Mumbai to Nashik Kumbh Package" },
      { slug: "pune-to-nashik-kumbh-package", title: "Pune to Nashik Kumbh Package" },
      { slug: "senior-citizen-nashik-kumbh-yatra", title: "Senior Citizen Assisted Nashik Kumbh Yatra" },
      { slug: "group-society-nashik-kumbh-package", title: "Group/Society Nashik Kumbh Package" },
      { slug: "premium-nashik-trimbakeshwar-stay", title: "Premium Nashik + Trimbakeshwar Stay Package" },
      { slug: "budget-nashik-kumbh-package", title: "Budget Nashik Kumbh Package" },
    ]
    : [
      { slug: "ujjain-kumbh-mahakal-darshan", title: "Ujjain Kumbh + Mahakal Darshan" },
      { slug: "indore-stay-ujjain-day-trip", title: "Indore Stay + Ujjain Kumbh Day Trip" },
      { slug: "ujjain-omkareshwar-maheshwar", title: "Ujjain + Omkareshwar + Maheshwar" },
      { slug: "senior-citizen-ujjain-kumbh-yatra", title: "Senior Citizen Assisted Ujjain Kumbh Yatra" },
      { slug: "group-society-ujjain-kumbh-package", title: "Group/Society Ujjain Kumbh Package" },
      { slug: "premium-ujjain-indore-stay", title: "Premium Ujjain/Indore Stay Package" },
      { slug: "budget-ujjain-kumbh-package", title: "Budget Ujjain Kumbh Package" },
    ];
}
