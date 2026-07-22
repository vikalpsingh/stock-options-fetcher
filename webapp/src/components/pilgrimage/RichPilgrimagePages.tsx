import Link from "next/link";
import { ArrowRight, BedDouble, CalendarDays, HeartHandshake, Landmark, MapPin, PackageCheck, Route, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { VerificationNote } from "@/src/components/common/VerificationNote";
import { TravelSearchWidget } from "@/src/components/travel/TravelSearchWidget";
import { PackageLeadForm } from "@/src/components/packages/PackageLeadForm";
import { charDhamGlobalNote, charDhamGuides, type CharDhamSite } from "@/src/data/charDhamGuides";
import { jyotirlingaGuides, type JyotirlingaSite } from "@/src/data/jyotirlingaGuides";
import { getPilgrimageServices } from "@/src/data/pilgrimageServices";
import { pilgrimageStories } from "@/src/data/pilgrimageStories";
import { getPilgrimageStats } from "@/src/data/pilgrimageStats";
import { pilgrimageFamousNames } from "@/src/data/pilgrimageFamousNames";
import { pilgrimageTravelRoutes } from "@/src/data/pilgrimageTravelRoutes";

type Pillar = "char-dham" | "jyotirlinga";

export const charDhamFaqs = [
  ["What is Char Dham Yatra?", "Uttarakhand Char Dham Yatra covers Yamunotri, Gangotri, Kedarnath and Badrinath."],
  ["Which temples are included in Uttarakhand Char Dham?", "Yamunotri, Gangotri, Kedarnath and Badrinath."],
  ["Is registration required for Char Dham Yatra?", "Yes, registration requirements should be verified through official Uttarakhand portals every season."],
  ["What is the best route order?", "The usual route order is Yamunotri, Gangotri, Kedarnath and Badrinath."],
  ["How many days are needed for Char Dham?", "A fast plan may take about 10 days; 12-14 days is more balanced, especially for families."],
  ["Is Char Dham suitable for senior citizens?", "It can be, but Kedarnath and Yamunotri need medical caution, assistance and buffer days."],
  ["Which part is most difficult?", "Kedarnath and Yamunotri are usually the most demanding due to trek/altitude and weather."],
  ["Is helicopter available for Kedarnath?", "Helicopter options are usually available subject to official booking, weather and availability."],
  ["What should I check before booking?", "Registration, health advisories, route status, weather, helicopter rules, hotel cancellation and official temple dates."],
  ["What is the difference between Char Dham and Do Dham?", "Do Dham usually means a shorter Kedarnath-Badrinath or two-temple plan, while Char Dham covers all four temples."],
].map(([question, answer]) => ({ question, answer }));

export const jyotirlingaFaqs = [
  ["What are the 12 Jyotirlingas?", "They are 12 revered Shiva temples across India associated with Shiva's infinite light tradition."],
  ["Which Jyotirlinga should I visit first?", "There is no single travel rule; many families start with the nearest regional circuit."],
  ["Can all 12 Jyotirlingas be covered in one trip?", "Yes, but it is usually tiring. Regional circuits are more practical."],
  ["Which Jyotirlingas are easiest for senior citizens?", "Somnath, Omkareshwar, Mahakaleshwar, Kashi Vishwanath, Trimbakeshwar, Rameshwaram and Grishneshwar can be easier depending on season and mobility."],
  ["Which Jyotirlinga is connected with Kumbh?", "Mahakaleshwar is connected with Ujjain Kumbh and Trimbakeshwar with Nashik-Trimbakeshwar Kumbh."],
  ["How many days are needed for 12 Jyotirlinga Darshan?", "A complete yatra may need multiple weeks; regional circuits can be done in 2-7 days."],
  ["What are the best regional circuits?", "MP, Maharashtra, Gujarat, North, South and East circuits are practical ways to plan."],
  ["Is Kedarnath Jyotirlinga difficult?", "Yes, it is high-altitude and requires serious health, route and weather planning."],
  ["Which Jyotirlingas can be combined with Ujjain/Nashik Kumbh?", "Mahakaleshwar and Omkareshwar with Ujjain; Trimbakeshwar with Nashik."],
  ["Are temple timings same throughout the year?", "No. Timings, aarti bookings and crowd rules vary by temple and festival season."],
].map(([question, answer]) => ({ question, answer }));

export function PillarHomePage({ pillar }: { pillar: Pillar }) {
  const isChar = pillar === "char-dham";
  const title = isChar ? "Char Dham Yatra Guide" : "12 Jyotirlinga Darshan Guide";
  const subtitle = isChar
    ? "Plan Char Dham Yatra with registration, route map, history, Kedarnath, Badrinath, Gangotri, Yamunotri, senior citizen tips, stay, transport and packages."
    : "Plan 12 Jyotirlinga Darshan across India with history, stories, routes, regional circuits, senior citizen tips, stay, transport and package guidance.";
  const sites = isChar ? charDhamGuides : jyotirlingaGuides;
  return (
    <main>
      <Hero eyebrow={isChar ? "Char Dham Yatra" : "12 Jyotirlinga"} title={title} subtitle={subtitle} primaryHref={isChar ? "/char-dham-yatra/route-map" : "/12-jyotirlinga/complete-itinerary"} secondaryHref={isChar ? "/char-dham-yatra/packages" : "/12-jyotirlinga/packages"} />
      <section className="bg-cream px-4 py-10 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><VerificationNote context={isChar ? "char-dham" : "jyotirlinga"} /></div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="Start here" title={isChar ? "Plan the four Himalayan dhams with care" : "Plan the 12 Shiva jyotirlingas by region"} text={isChar ? charDhamGlobalNote : "Most pilgrims complete 12 Jyotirlinga Darshan in multiple trips, not one rushed itinerary."} />
        <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-4">{sites.map((site) => <SiteMiniCard key={site.slug} pillar={pillar} site={site} />)}</div>
      </div></section>
      <StatsSection pillar={pillar} />
      <ServicesSection pillar={pillar} />
      <RoutesSection pillar={pillar} />
      <TravelAndPackage pillar={pillar} sourcePage={`${pillar}-home`} />
      <FAQBlock faqs={isChar ? charDhamFaqs : jyotirlingaFaqs} title={`${title} FAQs`} />
      <Schemas pillar={pillar} title={title} faqs={isChar ? charDhamFaqs : jyotirlingaFaqs} itemList />
    </main>
  );
}

export function PlaceGuidePage({ pillar, site }: { pillar: Pillar; site: CharDhamSite | JyotirlingaSite }) {
  const isChar = pillar === "char-dham";
  const quickFacts = isChar ? charFacts(site as CharDhamSite) : jyotiFacts(site as JyotirlingaSite);
  const packageHref = isChar ? "/char-dham-yatra/packages" : "/12-jyotirlinga/packages";
  return (
    <main>
      <Hero eyebrow={isChar ? "Char Dham site guide" : "Jyotirlinga temple guide"} title={site.templeName} subtitle={site.shortDescription} primaryHref="/travel-tools" secondaryHref={packageHref} />
      <section className="bg-cream px-4 py-10 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><VerificationNote context={isChar ? "char-dham" : "jyotirlinga"} /></div></section>
      <QuickFacts facts={quickFacts} />
      <StorySection stories={site.mythologyStories} notes={site.historicalNotes} />
      <ImportanceSection points={site.spiritualImportance} />
      <UsefulPlaces places={site.usefulPlaces} />
      <Tips title="Senior citizen suitability" suitability={isChar ? (site as CharDhamSite).seniorCitizenSuitability : (site as JyotirlingaSite).seniorCitizenSuitability} senior={site.seniorCitizenTips} family={site.familyTips} warnings={site.travellerWarnings} />
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><TravelSearchWidget title={`Search travel for ${site.templeName}`} sourcePage={`${pillar}-${site.slug}`} /></div></section>
      <PackageStrip title={`Need help planning ${site.templeName}?`} href={packageHref} />
      <FAQBlock faqs={siteFaqs(site.templeName, isChar)} title={`${site.templeName} FAQs`} />
      <Schemas pillar={pillar} title={site.templeName} faqs={siteFaqs(site.templeName, isChar)} />
    </main>
  );
}

export function HistoryStoriesPage({ pillar }: { pillar: Pillar }) {
  const isChar = pillar === "char-dham";
  const stories = isChar ? pilgrimageStories.charDham : pilgrimageStories.jyotirlinga;
  const famous = isChar ? pilgrimageFamousNames.charDham : pilgrimageFamousNames.jyotirlinga;
  return (
    <main>
      <Hero eyebrow={isChar ? "Char Dham history" : "Jyotirlinga history"} title={isChar ? "Char Dham Yatra History and Stories" : "12 Jyotirlinga History and Meaning"} subtitle={isChar ? "Understand the route order, traditional stories and why registration and health planning matter today." : "Understand Jyoti + Linga, the 12 sacred Shiva sites and how to plan them practically."} />
      <section className="bg-cream px-4 py-10 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><VerificationNote context={isChar ? "char-dham" : "jyotirlinga"} /></div></section>
      <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><div className="grid gap-5 md:grid-cols-3">{stories.map((story) => <InfoCard key={story.title} title={story.title} text={story.text} />)}</div></div></section>
      <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Names and traditions" title="Famous names, stories and institutions" /><div className="mt-8 grid gap-5 md:grid-cols-3">{famous.map((item) => <InfoCard key={item.name} title={item.name} text={`${item.role}: ${item.relevance}`} />)}</div></div></section>
      <FAQBlock faqs={isChar ? charDhamFaqs : jyotirlingaFaqs} title={isChar ? "Char Dham history FAQs" : "Jyotirlinga history FAQs"} />
      <Schemas pillar={pillar} title={isChar ? "Char Dham history" : "12 Jyotirlinga history"} faqs={isChar ? charDhamFaqs : jyotirlingaFaqs} article />
    </main>
  );
}

export function ServicesPage({ pillar }: { pillar: Pillar }) {
  return <main><Hero eyebrow="Useful services" title={pillar === "char-dham" ? "Char Dham Yatra Services Guide" : "12 Jyotirlinga Services Guide"} subtitle="Registration, stay, transport, medical, food, sanitation, crowd planning and package support." /><ServicesSection pillar={pillar} /><TravelAndPackage pillar={pillar} sourcePage={`${pillar}-services`} /><Disclaimer pillar={pillar} /></main>;
}

export function PackagesPage({ pillar }: { pillar: Pillar }) {
  const isChar = pillar === "char-dham";
  const categories = (isChar ? ["Complete Char Dham Yatra Package", "Char Dham Senior Citizen Assisted Package", "Kedarnath-Badrinath Package", "Do Dham Yatra Package", "Helicopter-Assisted Char Dham Planning", "Family Char Dham Package", "Group/Society Char Dham Package", "Premium Assisted Yatra", "Budget Char Dham Yatra"] : ["Complete 12 Jyotirlinga Darshan Package", "MP Jyotirlinga Circuit: Mahakaleshwar + Omkareshwar", "Maharashtra Jyotirlinga Circuit", "Gujarat Jyotirlinga Circuit", "Kashi + Kedarnath Shiva Circuit", "South Jyotirlinga Circuit", "Senior Citizen Jyotirlinga Yatra", "Family Jyotirlinga Trip", "Group/Society Jyotirlinga Package"]).map((title) => ({ slug: title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""), title }));
  return <main><Hero eyebrow="Package quote" title={isChar ? "Char Dham Yatra Packages" : "12 Jyotirlinga Darshan Packages"} subtitle="Compare assisted yatra options for families, senior citizens and groups. IndianKumbh.com does not operate tours directly." /><section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[.8fr_1.2fr]"><div><VerificationNote context={isChar ? "char-dham" : "jyotirlinga"} /><div className="mt-8 grid gap-4">{categories.map((category) => <InfoCard key={category.slug} title={category.title} text="Final price, availability, inclusions, cancellation, refund and service terms are confirmed by the partner." />)}</div></div><PackageLeadForm packageCategories={categories} destination={isChar ? "Char Dham Yatra" : "12 Jyotirlinga Darshan"} /></div></section><Disclaimer pillar={pillar} /></main>;
}

export function ItineraryPage({ pillar }: { pillar: Pillar }) {
  const isChar = pillar === "char-dham";
  const items = isChar
    ? ["Recommended order: Yamunotri → Gangotri → Kedarnath → Badrinath", "10-day fast itinerary", "12-14 day balanced itinerary", "Senior citizen slower itinerary", "Helicopter-assisted planning note", "Road journey and weather buffer note"]
    : ["Plan regional circuits instead of one rushed trip", "MP: Mahakaleshwar + Omkareshwar", "Maharashtra: Trimbakeshwar + Bhimashankar + Grishneshwar", "Gujarat: Somnath + Nageshwar + Dwarka", "North: Kashi Vishwanath + Kedarnath", "South: Mallikarjuna + Rameshwaram", "East: Vaidyanath", "7-day partial, 15-day regional and 30-day complete concepts"];
  return <main><Hero eyebrow="Itinerary" title={isChar ? "Char Dham Route Map" : "12 Jyotirlinga Complete Itinerary"} subtitle={isChar ? "Plan the Himalayan route with weather, health and buffer days." : "Plan the 12 Jyotirlingas by region for practical family travel."} /><section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{items.map((item) => <InfoCard key={item} title={item} text="Keep buffers, verify official rules and avoid overpacking the itinerary." />)}</div><div className="mt-10"><PackageStrip title="Want help turning this into a real yatra plan?" href={isChar ? "/char-dham-yatra/packages" : "/12-jyotirlinga/packages"} /></div></div></section></main>;
}

export function SeniorGuidePage({ pillar }: { pillar: Pillar }) {
  const isChar = pillar === "char-dham";
  const tips = isChar ? ["Medical fitness checklist", "High-altitude caution", "Kedarnath and Yamunotri difficulty notes", "Helicopter/pony/palki planning", "Keep buffer days", "Avoid monsoon and extreme crowd days", "Medicines and documents checklist", "Insurance and emergency contacts"] : ["Easier Jyotirlingas first", "Kedarnath is more difficult due to altitude/trek", "MP, Gujarat, Maharashtra and Varanasi circuits are practical", "Avoid peak Shravan Mondays and Maha Shivratri if crowd-sensitive", "Choose temple-near stay vs comfortable city hotel carefully", "Wheelchair/local assistance placeholders"];
  return <main><Hero eyebrow="Senior citizen guide" title={isChar ? "Char Dham Senior Citizen Guide" : "12 Jyotirlinga Senior Citizen Guide"} subtitle="A slower, safer pilgrimage plan for parents, elders and assisted family travel." /><section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><VerificationNote context={isChar ? "char-dham" : "jyotirlinga"} /><div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-4">{tips.map((tip) => <InfoCard key={tip} title={tip} text="Use this as a checklist item before booking travel." />)}</div></div></section><PackageStrip title="Need assisted senior citizen yatra planning?" href={isChar ? "/char-dham-yatra/packages" : "/12-jyotirlinga/packages"} /></main>;
}

export function RegistrationPage() {
  return <main><Hero eyebrow="Registration" title="Char Dham Yatra Registration Guide" subtitle="Registration, vehicle registration, health advisories and helicopter booking rules must be checked through official Uttarakhand portals." /><section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><VerificationNote context="char-dham" /><div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-4">{["Official yatra registration", "Vehicle registration", "Health registration/advisory", "Helicopter booking reference", "Weather alerts", "Documents checklist", "SMS/QR checks", "Avoid unofficial heli links"].map((item) => <InfoCard key={item} title={item} text="Verify this from official portals before booking hotels or transport." />)}</div></div></section></main>;
}

function Hero({ eyebrow, title, subtitle, primaryHref = "/travel-tools", secondaryHref = "/packages" }: { eyebrow: string; title: string; subtitle: string; primaryHref?: string; secondaryHref?: string }) {
  return <section className="brand-gradient temple-silhouette pattern-mandala px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28"><div className="mx-auto max-w-7xl"><p className="inline-flex rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-xs font-black uppercase tracking-[.18em] text-gold">{eyebrow}</p><h1 className="mt-6 max-w-5xl font-serif text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">{title}</h1><p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/90 sm:text-xl">{subtitle}</p><div className="mt-8 flex flex-col gap-3 sm:flex-row"><Button asChild size="lg"><Link href={primaryHref}>Plan travel<ArrowRight className="h-4 w-4" /></Link></Button><Button asChild variant="outline" size="lg"><Link href={secondaryHref}>Get package quote</Link></Button></div></div></section>;
}

function SectionTitle({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return <div className="max-w-3xl"><p className="text-xs font-black uppercase tracking-[.2em] text-saffron">{eyebrow}</p><h2 className="mt-3 font-serif text-4xl font-semibold leading-tight text-ink sm:text-5xl">{title}</h2>{text && <p className="mt-4 text-lg leading-8 text-stone-600">{text}</p>}</div>;
}

function InfoCard({ title, text }: { title: string; text: string }) {
  return <Card className="h-full border-gold/35 bg-[#fffdf8]"><CardContent><h3 className="font-serif text-2xl">{title}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{text}</p></CardContent></Card>;
}

function SiteMiniCard({ pillar, site }: { pillar: Pillar; site: CharDhamSite | JyotirlingaSite }) {
  const href = pillar === "char-dham" ? `/char-dham-yatra/${site.slug}` : `/12-jyotirlinga/${site.slug}`;
  const badge = pillar === "char-dham" ? (site as CharDhamSite).difficulty : (site as JyotirlingaSite).seniorCitizenSuitability;
  return <Link href={href} className="group"><Card className="h-full border-gold/35 transition group-hover:-translate-y-1 group-hover:border-saffron"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{badge}</p><h3 className="mt-3 font-serif text-2xl">{site.templeName}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{site.shortDescription}</p><span className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-maroon">View guide<ArrowRight className="h-4 w-4" /></span></CardContent></Card></Link>;
}

function QuickFacts({ facts }: { facts: [string, string][] }) {
  return <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Quick facts" title="Plan with the essentials first" /><div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{facts.map(([label, value]) => <Card key={label} className="border-gold/35"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{label}</p><p className="mt-2 font-serif text-2xl">{value}</p></CardContent></Card>)}</div></div></section>;
}

function charFacts(site: CharDhamSite): [string, string][] {
  return [["State", site.state], ["Main deity", site.deity], ["Base town", site.baseTown], ["Nearest airport", site.nearestAirport], ["Nearest railway station", site.nearestRailwayStation], ["Opening season", site.usualOpeningSeason], ["Difficulty", site.difficulty], ["Senior suitability", site.seniorCitizenSuitability]];
}

function jyotiFacts(site: JyotirlingaSite): [string, string][] {
  return [["State", site.state], ["Main deity", site.deityName], ["Nearest airport", site.nearestAirport], ["Nearest railway station", site.nearestRailwayStation], ["Best time", site.bestTimeToVisit], ["Suggested duration", site.suggestedDuration], ["Senior suitability", site.seniorCitizenSuitability], ["Circuit", site.partOfCircuit.join(", ")]];
}

function StorySection({ stories, notes }: { stories: { title: string; summary: string }[]; notes: { title: string; description: string }[] }) {
  return <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Story and history" title="Why this place matters spiritually" /><div className="mt-8 grid gap-5 md:grid-cols-2">{[...stories.map((s) => ({ title: s.title, text: s.summary })), ...notes.map((n) => ({ title: n.title, text: n.description }))].map((item) => <InfoCard key={item.title} title={item.title} text={item.text} />)}</div></div></section>;
}

function ImportanceSection({ points }: { points: string[] }) {
  return <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Sacred importance" title="Spiritual planning anchors" /><div className="mt-8 grid gap-5 md:grid-cols-3">{points.map((point) => <InfoCard key={point} title={point} text="Use this as a meaningful anchor while keeping the practical plan realistic." />)}</div></div></section>;
}

function UsefulPlaces({ places }: { places: (CharDhamSite | JyotirlingaSite)["usefulPlaces"] }) {
  return <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Nearby places" title="Temple, base town and circuit places" /><div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{places.map((place) => <Card key={place.name} className="border-gold/35"><CardContent><p className="text-xs font-black uppercase tracking-wider text-saffron">{place.type.replaceAll("_", " ")}</p><h3 className="mt-2 font-serif text-2xl">{place.name}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{place.importance}</p><p className="mt-3 rounded-2xl bg-cream p-3 text-xs leading-5 text-stone-600">{place.travellerTip}</p>{place.seniorCitizenNote && <p className="mt-2 text-xs font-semibold text-maroon">{place.seniorCitizenNote}</p>}</CardContent></Card>)}</div></div></section>;
}

function Tips({ title, suitability, senior, family, warnings }: { title: string; suitability: string; senior: string[]; family: string[]; warnings: string[] }) {
  return <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Family and senior planning" title={`${title}: ${suitability}`} /><div className="mt-8 grid gap-5 md:grid-cols-3"><Checklist title="Senior citizen tips" items={senior} icon="senior" /><Checklist title="Family travel tips" items={family} icon="family" /><Checklist title="What to verify/avoid" items={warnings} icon="warning" /></div></div></section>;
}

function Checklist({ title, items, icon }: { title: string; items: string[]; icon: "senior" | "family" | "warning" }) {
  const Icon = icon === "senior" ? HeartHandshake : icon === "family" ? ShieldCheck : CalendarDays;
  return <Card className="border-gold/35"><CardContent><Icon className="h-6 w-6 text-saffron" /><h3 className="mt-4 font-serif text-2xl">{title}</h3><ul className="mt-4 space-y-3 text-sm leading-7 text-stone-600">{items.map((item) => <li key={item}>• {item}</li>)}</ul></CardContent></Card>;
}

function ServicesSection({ pillar }: { pillar: Pillar }) {
  const groups = getPilgrimageServices(pillar);
  return <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Useful services" title="Services pilgrims should plan before travel" /><div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{groups.map((group) => <Card key={group.title} className="border-gold/35 bg-white"><CardContent><h3 className="font-serif text-2xl">{group.title}</h3><ul className="mt-4 space-y-2 text-sm text-stone-600">{group.items.map((item) => <li key={item}>• {item}</li>)}</ul><p className="mt-4 rounded-2xl bg-amber-50 p-3 text-xs leading-5 text-amber-950">{group.note}</p></CardContent></Card>)}</div></div></section>;
}

function StatsSection({ pillar }: { pillar: Pillar }) {
  const stats = getPilgrimageStats(pillar === "char-dham" ? "char-dham-yatra" : "12-jyotirlinga");
  if (!stats) return null;
  return <section className="bg-sand px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><VerificationNote context={pillar === "char-dham" ? "char-dham" : "jyotirlinga"} /><SectionTitle eyebrow="Travel scale" title={stats.title} /><div className="mt-8 grid gap-5 md:grid-cols-2">{stats.latestKnownStats.map((item) => <InfoCard key={item.label} title={`${item.label}: ${item.value}`} text={item.note} />)}</div><div className="mt-8 grid gap-4 md:grid-cols-3">{stats.planningTakeaways.map((item) => <InfoCard key={item} title="Planning takeaway" text={item} />)}</div></div></section>;
}

function RoutesSection({ pillar }: { pillar: Pillar }) {
  const routes = pilgrimageTravelRoutes.filter((route) => route.pillar === pillar);
  return <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><SectionTitle eyebrow="Route planning" title="Practical route ideas" /><div className="mt-8 grid gap-5 md:grid-cols-3">{routes.map((route) => <Link key={route.id} href={route.href} className="group"><Card className="h-full border-gold/35 transition group-hover:-translate-y-1 group-hover:border-saffron"><CardContent><Route className="h-6 w-6 text-saffron" /><h3 className="mt-4 font-serif text-2xl">{route.title}</h3><p className="mt-2 text-sm font-semibold text-maroon">{route.startCity} → {route.endCity}</p><p className="mt-3 text-sm leading-7 text-stone-600">{route.advice}</p></CardContent></Card></Link>)}</div></div></section>;
}

function TravelAndPackage({ pillar, sourcePage }: { pillar: Pillar; sourcePage: string }) {
  return <section className="bg-white px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><TravelSearchWidget title={pillar === "char-dham" ? "Search Char Dham travel options" : "Search Jyotirlinga travel options"} sourcePage={sourcePage} /></div></section>;
}

function PackageStrip({ title, href }: { title: string; href: string }) {
  return <section className="bg-maroon px-4 py-12 text-white sm:px-6 lg:px-8"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-6 md:flex-row md:items-center"><div><p className="text-xs font-black uppercase tracking-[.2em] text-gold">Package support</p><h2 className="mt-2 font-serif text-3xl text-white">{title}</h2><p className="mt-3 text-sm leading-7 text-orange-50/85">IndianKumbh.com does not operate tours directly. Packages are fulfilled by independent travel partners.</p></div><Button asChild size="lg"><Link href={href}><PackageCheck className="h-4 w-4" />Get package quote</Link></Button></div></section>;
}

function Disclaimer({ pillar }: { pillar: Pillar }) {
  return <section className="bg-amber-50 px-4 py-6 text-sm leading-7 text-amber-950 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl">{pillar === "char-dham" ? "Service availability, temple rules, registration rules, weather, route status and transport availability can change. Verify with official sources before travel." : "Darshan booking, temple rules, special aarti, crowd restrictions and local services can change. Verify with official temple sources before travel."}</div></section>;
}

function FAQBlock({ faqs, title }: { faqs: { question: string; answer: string }[]; title: string }) {
  return <section className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-5xl"><SectionTitle eyebrow="FAQs" title={title} /><div className="mt-8 space-y-4">{faqs.map((faq) => <Card key={faq.question} className="border-gold/35"><CardContent><h3 className="font-serif text-xl">{faq.question}</h3><p className="mt-3 text-sm leading-7 text-stone-600">{faq.answer}</p></CardContent></Card>)}</div></div></section>;
}

function siteFaqs(name: string, isChar: boolean) {
  return [
    { question: `Why is ${name} important?`, answer: isChar ? "It is one of the four Uttarakhand Char Dham pilgrimage stops." : "It is one of the 12 revered Jyotirlinga temples." },
    { question: "How should families plan?", answer: "Keep the itinerary simple, choose suitable stay, avoid peak crowd rush and verify official rules before travel." },
    { question: "Is it suitable for senior citizens?", answer: "It depends on mobility, season, crowd and route conditions. Use the senior tips and consult a doctor for difficult/high-altitude routes." },
    { question: "What should be verified?", answer: "Temple timings, registration rules, routes, weather, darshan booking, transport and local services." },
  ];
}

function Schemas({ pillar, title, faqs, article = false, itemList = false }: { pillar: Pillar; title: string; faqs: { question: string; answer: string }[]; article?: boolean; itemList?: boolean }) {
  const faqSchema = { "@context": "https://schema.org", "@type": "FAQPage", mainEntity: faqs.map((faq) => ({ "@type": "Question", name: faq.question, acceptedAnswer: { "@type": "Answer", text: faq.answer } })) };
  const breadcrumbSchema = { "@context": "https://schema.org", "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: "Home", item: "https://indiankumbh.com/" }, { "@type": "ListItem", position: 2, name: pillar === "char-dham" ? "Char Dham Yatra" : "12 Jyotirlinga", item: `https://indiankumbh.com/${pillar === "char-dham" ? "char-dham-yatra" : "12-jyotirlinga"}` }] };
  const articleSchema = article ? { "@context": "https://schema.org", "@type": "Article", headline: title } : null;
  const list = itemList ? { "@context": "https://schema.org", "@type": "ItemList", name: title, itemListElement: (pillar === "char-dham" ? charDhamGuides : jyotirlingaGuides).map((item, index) => ({ "@type": "ListItem", position: index + 1, name: item.templeName })) } : null;
  return <><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} /><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbSchema) }} />{articleSchema && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(articleSchema) }} />}{list && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(list) }} />}</>;
}
