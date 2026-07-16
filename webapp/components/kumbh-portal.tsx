import Image from "next/image";
import Link from "next/link";
import { ArrowRight, BedDouble, CalendarDays, Check, Landmark, MapPin, MapPinned, Route, Sparkles, Utensils } from "lucide-react";
import type { PortalLocale } from "@/data/kumbh-portal";
import { latestGuides, portalCopy } from "@/data/kumbh-portal";
import { getKumbhSite, kumbhSites, type KumbhSite } from "@/src/data/kumbhSites";
import { uiCopy } from "@/data/locale-ui";
import { localizedHref } from "@/lib/locale";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { HomepagePackageCTA } from "@/src/components/packages/HomepagePackageCTA";
import { HotelBookingCTA } from "@/src/components/travel/HotelBookingCTA";
import { HotelSearchBox } from "@/src/components/travel/HotelSearchBox";
import { TravelSearchWidget } from "@/src/components/travel/TravelSearchWidget";
import { pilgrimagePillars } from "@/src/data/pilgrimagePillars";
import { kumbhEvents } from "@/src/data/kumbhEvents";
import { sacredCities } from "@/src/data/sacredCities";

export function NationalKumbhHome({ locale = "en" }: { locale?: PortalLocale }) {
  if (locale === "en") return <EnglishPilgrimageHome />;
  const copy = portalCopy[locale];
  const regional = uiCopy[locale];
  const href = (path: string) => localizedHref(path, locale);
  const featuredCards = [
    { title: regional.nav[1], description: regional.sectionDescription, href: "/mahakal-temple-guide", icon: Landmark },
    { title: regional.compareStays, description: regional.sectionDescription, href: "/stay-guide", icon: BedDouble },
    { title: regional.planTrip, description: regional.plannerDescription, href: "/plan-my-trip", icon: Route },
    { title: regional.itineraries, description: regional.sectionDescription, href: "/itineraries", icon: CalendarDays },
    { title: regional.foodGuide, description: regional.sectionDescription, href: "/food-guide", icon: Utensils },
    { title: regional.nearby, description: regional.sectionDescription, href: "/nearby-places", icon: MapPinned },
  ];
  const upcomingSites = kumbhSites.filter((site) => site.status !== "featured");
  const featuredSite = kumbhSites.find((site) => site.status === "featured")!;

  return <main>
    <section className="temple-silhouette relative min-h-[720px] overflow-hidden bg-maroon text-white">
      <Image src="/images/mahakal-ghat-temple.png" alt={featuredSite.imageAlt} fill priority className="object-cover object-[62%_center]" sizes="100vw" />
      <div className="absolute inset-0 bg-gradient-to-r from-[#19080a]/95 via-[#50171b]/84 to-[#641f26]/30" /><div className="absolute inset-0 bg-gradient-to-t from-[#260d0f]/85 via-transparent to-black/15" /><div className="pattern-mandala absolute inset-0 opacity-10" />
      <div className="relative mx-auto flex min-h-[720px] max-w-7xl items-center px-4 py-20 sm:px-6 lg:px-8"><div className="max-w-4xl">
        <p className="inline-flex items-center gap-2 rounded-full border border-gold/40 bg-black/20 px-4 py-2 text-xs font-bold uppercase tracking-[.15em] text-gold"><Sparkles className="h-4 w-4" />{copy.heroEyebrow}</p>
        <h1 className="mt-6 text-balance font-serif text-5xl font-semibold leading-[1.04] sm:text-6xl lg:text-7xl">{copy.heroTitle}</h1>
        <p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/90 sm:text-xl">{copy.heroDescription}</p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row"><Button asChild size="lg"><Link href={href("/plan-my-trip")}>{copy.primaryCta}</Link></Button><Button asChild variant="outline" size="lg"><Link href={href("/kumbh-calendar")}>{copy.upcomingTitle}</Link></Button></div>
      </div></div>
    </section>

    <section className="border-y border-gold/25 bg-white px-4 py-5"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-center gap-x-4 gap-y-2 text-sm font-bold text-maroon sm:text-base">{copy.fourCities.map((city, index) => <span key={city.city} className="contents"><span>{city.city}</span>{index < copy.fourCities.length - 1 && <span className="text-gold">•</span>}</span>)}</div></section>

    <section className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
      <p className="text-xs font-bold uppercase tracking-[.2em] text-saffron">{copy.heroEyebrow}</p><h2 className="mt-3 max-w-3xl font-serif text-4xl font-semibold text-ink sm:text-5xl">{copy.heroTitle}</h2><p className="mt-4 max-w-3xl text-lg leading-8 text-stone-600">{copy.heroDescription}</p>
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{featuredCards.map(({ icon: Icon, ...card }) => <Link key={card.href} href={href(card.href)} className="group"><Card className="premium-card h-full border-gold/30 transition group-hover:-translate-y-1 group-hover:border-saffron/50"><CardContent><span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-50 text-saffron"><Icon className="h-6 w-6" /></span><h3 className="mt-5 font-serif text-2xl">{card.title}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{card.description}</p><span className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-maroon">{copy.readGuide}<ArrowRight className="h-4 w-4" /></span></CardContent></Card></Link>)}</div>
    </div></section>

    <section id="all-kumbhs" className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
      <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end"><div><p className="text-xs font-bold uppercase tracking-[.2em] text-saffron">{copy.upcomingEyebrow}</p><h2 className="mt-3 font-serif text-4xl font-semibold text-ink sm:text-5xl">{copy.upcomingTitle}</h2></div><Link href={href("/ujjain-kumbh-2028")} className="inline-flex items-center gap-2 text-sm font-bold text-maroon">{copy.heroEyebrow}: {featuredSite.name}<ArrowRight className="h-4 w-4" /></Link></div>
      <div className="mt-10 grid gap-5 md:grid-cols-3">{upcomingSites.map((item) => <KumbhCard key={item.slug} item={item} href={href(`/${item.slug}`)} readLabel={copy.readGuide} pendingLabel={copy.schedulePending} />)}</div>
    </div></section>

    <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><div className="flex flex-col justify-between gap-5 md:flex-row md:items-end"><div><p className="text-xs font-bold uppercase tracking-[.2em] text-saffron">Kumbh Calendar</p><h2 className="mt-3 font-serif text-4xl font-semibold sm:text-5xl">Planning status at a glance</h2></div><Button asChild variant="outline"><Link href={href("/kumbh-calendar")}>View full calendar<ArrowRight className="h-4 w-4" /></Link></Button></div><div className="mt-10 overflow-hidden rounded-3xl border border-gold/35 bg-white shadow-soft">{kumbhSites.map((site) => <div key={site.slug} className="grid gap-3 border-b border-stone-200 p-5 last:border-b-0 md:grid-cols-[1.2fr_.8fr_1.6fr] md:items-center sm:p-6"><div><h3 className="font-serif text-xl">{site.nextEventName}</h3><p className="mt-1 text-xs font-semibold text-stone-500">{site.city}, {site.state}</p></div><p className="text-sm font-bold text-saffron">{site.nextEventYear ?? "Future date"}</p><div><span className={`inline-flex rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-wider ${site.status === "featured" ? "bg-orange-50 text-saffron" : site.status === "upcoming" ? "bg-amber-50 text-amber-800" : "bg-stone-100 text-stone-600"}`}>{site.status}</span><p className="mt-2 text-xs leading-5 text-stone-500">{site.tentativeDates}</p></div></div>)}</div></div></section>

    <section id="latest-guides" className="pattern-mandala scroll-mt-28 bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><p className="text-xs font-bold uppercase tracking-[.2em] text-saffron">{copy.latestTitle}</p><h2 className="mt-3 font-serif text-4xl font-semibold sm:text-5xl">{copy.upcomingDescription}</h2><div className="mt-10 grid gap-5 md:grid-cols-3">{latestGuides.map((guide) => <Link key={guide.href} href={href(guide.href)} className="group"><Card className="h-full transition group-hover:-translate-y-1 group-hover:border-saffron/40"><CardContent><p className="text-xs font-bold uppercase tracking-widest text-saffron">{guide.category}</p><h3 className="mt-3 font-serif text-2xl leading-tight">{guide.title}</h3><p className="mt-4 text-sm leading-7 text-stone-600">{copy.whyDescription}</p><span className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-maroon">{copy.readGuide}<ArrowRight className="h-4 w-4" /></span></CardContent></Card></Link>)}</div></div></section>
  </main>;
}

function KumbhCard({ item, href, readLabel, pendingLabel }: { item: KumbhSite; href: string; readLabel: string; pendingLabel: string }) {
  return <Card className={`h-full overflow-hidden ${item.status === "featured" ? "border-saffron ring-2 ring-orange-100" : "border-gold/30"}`}><div className="brand-gradient pattern-jaali p-6 text-white"><div className="flex items-center justify-between"><MapPin className="h-6 w-6 text-gold" /><span className="rounded-full border border-white/20 bg-black/15 px-3 py-1 text-xs font-bold">{item.nextEventYear ?? "Future"}</span></div><h3 className="mt-8 font-serif text-2xl text-white">{item.name}</h3><p className="mt-1 text-xs text-orange-100">{item.river} · {item.state}</p></div><CardContent><p className="text-sm leading-7 text-stone-600">{item.shortDescription}</p><p className="mt-5 flex gap-2 rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-900"><CalendarDays className="h-4 w-4 shrink-0" />{pendingLabel}: {item.tentativeDates}</p><Button asChild variant="outline" className="mt-5 w-full"><Link href={href}>{item.mainCTA || readLabel}<ArrowRight className="h-4 w-4" /></Link></Button></CardContent></Card>;
}

export function KumbhGuidePage({ slug, locale = "en" }: { slug: string; locale?: PortalLocale }) {
  const copy = portalCopy[locale];
  const href = (path: string) => localizedHref(path, locale);
  if (slug === "kumbh-calendar") return <CalendarPage locale={locale} />;
  const item = getKumbhSite(slug);
  if (!item) return null;
  const isUjjain = item.status === "featured";
  return <main><section className="brand-gradient temple-silhouette pattern-mandala px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28"><div className="mx-auto max-w-7xl"><p className="text-xs font-bold uppercase tracking-[.2em] text-gold">{item.status} · {item.nextEventYear ?? "Future guide"}</p><h1 className="mt-4 max-w-4xl font-serif text-5xl sm:text-6xl">{item.name}</h1><p className="mt-5 max-w-3xl text-lg leading-8 text-orange-50/85">{item.shortDescription}</p><div className="mt-8 flex flex-wrap gap-3"><Button asChild size="lg"><Link href={isUjjain ? href("/plan-my-trip") : href("/kumbh-calendar")}>{isUjjain ? copy.primaryCta : copy.readGuide}</Link></Button>{isUjjain && <Button asChild variant="outline" size="lg"><Link href={href("/mahakal-temple-guide")}>Mahakal Guide</Link></Button>}</div></div></section>
    <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[1fr_360px]"><div className="space-y-6"><Info title="Planning status" text={item.tentativeDates} /><Info title="Sacred geography" text={`${item.city}, ${item.state}, is associated with the ${item.river}. Build the journey around official access plans, realistic walking time and family rest windows.`} /><Info title={isUjjain ? "Deep Ujjain planning" : "Guide under development"} text={isUjjain ? "Continue into Mahakal darshan, stay comparison, the trip planner, nearby destinations, itineraries and the food guide." : "This page establishes the evergreen city overview. Detailed stays, transport, bathing-day and crowd guidance will be added after authoritative information is available."} /></div><aside><Card className="premium-card border-gold/40"><CardContent><h2 className="font-serif text-2xl">Key attractions</h2><ul className="mt-5 space-y-3">{item.keyAttractions.map((text) => <li key={text} className="flex gap-2 text-sm text-stone-700"><Check className="h-4 w-4 text-saffron" />{text}</li>)}</ul></CardContent></Card></aside></div></section>
  </main>;
}

function CalendarPage({ locale }: { locale: PortalLocale }) {
  const copy = portalCopy[locale];
  return <main><section className="brand-gradient temple-silhouette px-4 py-20 text-white sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><p className="text-xs font-bold uppercase tracking-[.2em] text-gold">National planning calendar</p><h1 className="mt-4 font-serif text-5xl sm:text-6xl">Kumbh Calendar</h1><p className="mt-5 max-w-3xl text-lg leading-8 text-orange-50/85">A cautious planning view for upcoming and future Kumbh guides. Dates remain unconfirmed until official authorities publish them.</p></div></section><section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-6xl space-y-4">{kumbhSites.map((entry) => <Card key={entry.slug}><CardContent className="grid gap-4 md:grid-cols-[1fr_180px_1.5fr] md:items-center"><div><h2 className="font-serif text-2xl">{entry.name}</h2><p className="text-sm text-saffron">{entry.nextEventName} · {entry.nextEventYear ?? "Future"}</p></div><span className="rounded-full bg-amber-50 px-3 py-2 text-center text-xs font-bold text-amber-900">{copy.schedulePending}</span><p className="text-sm leading-6 text-stone-600">{entry.tentativeDates}</p></CardContent></Card>)}</div></section></main>;
}

function Info({ title, text }: { title: string; text: string }) {
  return <Card className="premium-card border-gold/30"><CardContent><h2 className="font-serif text-3xl">{title}</h2><p className="mt-4 leading-8 text-stone-600">{text}</p></CardContent></Card>;
}

function EnglishPilgrimageHome() {
  const current = kumbhEvents.find((event) => event.status === "current_focus")!;
  const next = kumbhEvents.find((event) => event.status === "next_focus")!;
  const heroCards = [
    { title: "Nashik-Trimbakeshwar Kumbh 2027", badge: "Current Focus", href: "/kumbh-mela/nashik-kumbh-2027", cta: "View Nashik Guide" },
    { title: "Ujjain Simhastha Kumbh 2028", badge: "Next Major Guide", href: "/kumbh-mela/ujjain-kumbh-2028", cta: "View Ujjain Guide" },
    { title: "Char Dham Yatra", badge: "Seasonal Yatra", href: "/char-dham-yatra", cta: "View Char Dham Guide" },
    { title: "12 Jyotirlinga Darshan", badge: "Evergreen Pilgrimage", href: "/12-jyotirlinga", cta: "View Jyotirlinga Guide" },
  ];
  const popularGuides = [
    ["Char Dham Yatra Registration", "/char-dham-yatra/registration"],
    ["12 Jyotirlinga Complete Route", "/12-jyotirlinga/complete-itinerary"],
    ["Mahakaleshwar + Omkareshwar Itinerary", "/temple-circuits/ujjain-omkareshwar-maheshwar"],
    ["Nashik + Trimbakeshwar + Shirdi", "/temple-circuits/nashik-trimbakeshwar-shirdi"],
    ["Senior Citizen Yatra Guide", "/senior-citizen-yatra"],
    ["Temple Trips from Bangalore", "/travel-tools"],
  ];
  const needs = ["Family Trip", "Senior Citizen Yatra", "Group/Society Yatra", "Weekend Temple Trip", "Budget Pilgrimage", "Premium Assisted Yatra"];
  return <main>
    <section className="temple-silhouette relative overflow-hidden bg-maroon px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28">
      <div className="pattern-mandala absolute inset-0 opacity-10" />
      <div className="relative mx-auto grid max-w-7xl gap-10 lg:grid-cols-[.95fr_1.05fr] lg:items-center">
        <div><p className="inline-flex rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-xs font-black uppercase tracking-[.18em] text-gold">IndianKumbh.com</p><h1 className="mt-6 font-serif text-5xl font-semibold leading-[1.04] sm:text-6xl lg:text-7xl">Plan India’s Sacred Yatras</h1><p className="mt-6 text-lg leading-8 text-orange-50/90 sm:text-xl">Kumbh Mela, Jyotirlinga, Char Dham and temple circuit guides for families, senior citizens and group pilgrims.</p><div className="mt-8 flex flex-col gap-3 sm:flex-row"><Button asChild size="lg"><Link href="/kumbh-mela/nashik-kumbh-2027">Explore Nashik Kumbh 2027<ArrowRight className="h-4 w-4" /></Link></Button><Button asChild variant="outline" size="lg"><Link href="/kumbh-mela/ujjain-kumbh-2028">Plan Ujjain Kumbh 2028</Link></Button></div></div>
        <div className="grid gap-4 sm:grid-cols-2">{heroCards.map((card) => <Link key={card.href} href={card.href} className="group rounded-3xl border border-white/15 bg-white/10 p-5 backdrop-blur transition hover:-translate-y-1 hover:bg-white/15"><p className="text-[10px] font-black uppercase tracking-wider text-gold">{card.badge}</p><h2 className="mt-3 font-serif text-2xl text-white">{card.title}</h2><span className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-orange-50">{card.cta}<ArrowRight className="h-4 w-4" /></span></Link>)}</div>
      </div>
    </section>
    <section className="border-y border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-950 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl">IndianKumbh.com is an information and travel discovery platform. Verify official dates, temple timings and travel rules before booking.</div></section>
    <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><HomeTitle eyebrow="Current and next focus" title="Kumbh guides to plan first" text="Nashik-Trimbakeshwar is the current focus because it is nearer. Ujjain Simhastha remains the next major deep planning guide." /><div className="mt-8 grid gap-5 md:grid-cols-2"><FocusCard title="Current Focus: Nashik-Trimbakeshwar Kumbh 2027" text={current.keyDates} href="/kumbh-mela/nashik-kumbh-2027" items={["Trimbakeshwar Jyotirlinga", "Ramkund", "Godavari snan", "Nashik vs Trimbakeshwar stay", "Nashik + Shirdi package"]} /><FocusCard title="Next Major Focus: Ujjain Simhastha Kumbh 2028" text={next.shortDescription} href="/kumbh-mela/ujjain-kumbh-2028" items={["Mahakaleshwar Jyotirlinga", "Shipra snan", "Ram Ghat", "Ujjain vs Indore stay", "Ujjain + Omkareshwar itinerary"]} /></div></div></section>
    <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><HomeTitle eyebrow="Popular pilgrimage guides" title="Start with the journey type" /><div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{popularGuides.map(([title, href]) => <GuideCard key={href} title={title} href={href} />)}</div></div></section>
    <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><HomeTitle eyebrow="Plan by destination" title="Sacred city guides" /><div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{sacredCities.slice(0, 8).map((city) => <GuideCard key={city.slug} title={city.city} href={`/sacred-cities/${city.slug}`} small />)}</div></div></section>
    <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><HomeTitle eyebrow="Plan by need" title="Choose the support your group needs" /><div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{needs.map((need) => <Card key={need} className="border-gold/35"><CardContent><h3 className="font-serif text-2xl">{need}</h3><p className="mt-3 text-sm leading-7 text-stone-600">Use travel tools and package support to build a practical, verified yatra plan.</p></CardContent></Card>)}</div></div></section>
    <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><HomeTitle eyebrow="Travel tools" title="Hotels, buses, flights, trains and package quotes" /><div className="mt-10"><TravelSearchWidget title="Plan your pilgrimage travel" sourcePage="homepage-pilgrimage" /></div></div></section>
    <section id="latest-guides" className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><HomeTitle eyebrow="Latest guides" title="Practical guides being built" /><div className="mt-10 grid gap-5 md:grid-cols-3">{pilgrimagePillars.slice(0, 6).map((pillar) => <GuideCard key={pillar.slug} title={pillar.title} href={`/${pillar.slug}`} />)}</div></div></section>
  </main>;
}

function HomeTitle({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return <div className="max-w-3xl"><p className="text-xs font-black uppercase tracking-[.2em] text-saffron">{eyebrow}</p><h2 className="mt-3 font-serif text-4xl font-semibold leading-tight text-ink sm:text-5xl">{title}</h2>{text && <p className="mt-4 text-lg leading-8 text-stone-600">{text}</p>}</div>;
}

function FocusCard({ title, text, href, items = [] }: { title: string; text: string; href: string; items?: string[] }) {
  return <Link href={href} className="group"><Card className="h-full border-gold/35 bg-[#fffdf8] transition group-hover:-translate-y-1 group-hover:border-saffron"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">Focus guide</p><h3 className="mt-3 font-serif text-3xl">{title}</h3><p className="mt-4 text-sm leading-7 text-stone-600">{text}</p>{items.length > 0 && <ul className="mt-5 grid gap-2 text-sm font-semibold text-stone-700 sm:grid-cols-2">{items.map((item) => <li key={item} className="rounded-full border border-gold/30 bg-cream px-3 py-2">{item}</li>)}</ul>}<span className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-maroon">Open guide<ArrowRight className="h-4 w-4" /></span></CardContent></Card></Link>;
}

function GuideCard({ title, href, small = false }: { title: string; href: string; small?: boolean }) {
  return <Link href={href} className="group"><Card className="h-full border-gold/35 transition group-hover:-translate-y-1 group-hover:border-saffron"><CardContent><h3 className={`font-serif ${small ? "text-xl" : "text-2xl"}`}>{title}</h3><p className="mt-3 text-sm leading-7 text-stone-600">Practical route, stay, senior citizen and booking guidance.</p><span className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-maroon">View guide<ArrowRight className="h-4 w-4" /></span></CardContent></Card></Link>;
}
