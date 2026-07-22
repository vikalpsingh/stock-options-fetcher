import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { HindiPageTemplate } from "@/components/hindi-page";
import { HindiTripPlanner } from "@/components/hindi-trip-planner";
import { HindiContact } from "@/components/hindi-contact";
import { KumbhGuidePage } from "@/components/kumbh-portal";
import { regionalPages } from "@/data/regional-pages";
import { uiCopy } from "@/data/locale-ui";
import { isLocaleCode, localeCodes } from "@/lib/locale";
import { portalCopy } from "@/data/kumbh-portal";
import { LocalizedPilgrimagePage, localizedPilgrimageTitle } from "@/src/components/pilgrimage/LocalizedPilgrimagePages";
import { TravelSearchWidget } from "@/src/components/travel/TravelSearchWidget";
import { charDhamGuides } from "@/src/data/charDhamGuides";
import { jyotirlingaGuides } from "@/src/data/jyotirlingaGuides";
import { kumbhGuides } from "@/src/data/kumbhGuides";

type Props = { params: Promise<{ locale: string; slug: string[] }> };

export function generateStaticParams() {
  const charSections = ["history", "registration", "route-map", "how-to-reach", "stay", "services", "senior-citizen-guide", "packages", "faqs"];
  const jyotiSections = ["history", "complete-itinerary", "how-to-reach", "services", "senior-citizen-guide", "packages", "faqs"];
  const kumbhSections = ["history", "places", "how-to-reach", "stay", "services", "packages", "faqs"];
  const slugs = [
    ...Object.keys(regionalPages.hi).map((slug) => [slug]),
    ...["plan-my-trip", "contact", "travel-tools", "ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh", "kumbh-calendar"].map((slug) => [slug]),
    ["kumbh-mela"],
    ...kumbhGuides.map((guide) => ["kumbh-mela", guide.slug]),
    ...kumbhGuides.flatMap((guide) => kumbhSections.map((section) => ["kumbh-mela", guide.slug, section])),
    ["char-dham-yatra"],
    ...charSections.map((section) => ["char-dham-yatra", section]),
    ...charDhamGuides.map((site) => ["char-dham-yatra", site.slug]),
    ["12-jyotirlinga"],
    ...jyotiSections.map((section) => ["12-jyotirlinga", section]),
    ...jyotirlingaGuides.map((site) => ["12-jyotirlinga", site.slug]),
  ];
  return localeCodes.flatMap((locale) => slugs.map((slug) => ({ locale, slug })));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale, slug } = await params;
  if (!isLocaleCode(locale)) return {};
  const key = slug.join("/");
  const copy = uiCopy[locale];
  const content = regionalPages[locale][key];
  if (key.startsWith("kumbh-mela") || key.startsWith("char-dham-yatra") || key.startsWith("12-jyotirlinga")) {
    const title = localizedPilgrimageTitle(locale, key);
    return { title, description: `${title} · ${copy.footerText}`, alternates: { canonical: `/${locale}/${key}`, languages: Object.fromEntries([["en", `/${key}`], ...localeCodes.map((code) => [code, `/${code}/${key}`])]) } };
  }
  const portalSlugs = ["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh", "kumbh-calendar"];
  if (key === "travel-tools") {
    return { title: `${copy.planTrip} | IndianKumbh`, description: copy.plannerDescription, alternates: { canonical: `/${locale}/travel-tools`, languages: Object.fromEntries([["en", "/travel-tools"], ...localeCodes.map((code) => [code, `/${code}/travel-tools`])]) } };
  }
  if (portalSlugs.includes(key)) {
    const portal = portalCopy[locale];
    return { title: `${portal.brand} · ${key.replaceAll("-", " ")}`, description: portal.upcomingDescription, alternates: { canonical: `/${locale}/${key}`, languages: Object.fromEntries([["en", `/${key}`], ...localeCodes.map((code) => [code, `/${code}/${key}`])]) } };
  }
  const title = key === "plan-my-trip" ? copy.plannerTitle : key === "contact" ? copy.enquiry : content?.title;
  const description = key === "plan-my-trip" ? copy.plannerDescription : content?.description || copy.footerText;
  return {
    title,
    description,
    alternates: { canonical: `/${locale}/${key}`, languages: Object.fromEntries([["en", `/${key}`], ...localeCodes.map((code) => [code, `/${code}/${key}`])]) },
  };
}

export default async function RegionalRoutePage({ params }: Props) {
  const { locale, slug } = await params;
  const key = slug.join("/");
  if (locale === "en") redirect(`/${key}`);
  if (!isLocaleCode(locale)) notFound();
  const copy = uiCopy[locale];
  if (key === "plan-my-trip") return <main className="pattern-mandala bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="mx-auto max-w-7xl"><p className="text-xs font-bold uppercase tracking-[.2em] text-saffron">{copy.planTrip}</p><h1 className="mt-3 max-w-4xl font-serif text-5xl font-semibold leading-tight text-ink sm:text-6xl">{copy.plannerTitle}</h1><p className="mt-5 max-w-3xl text-lg leading-8 text-stone-600">{copy.plannerDescription}</p><div className="mt-12"><HindiTripPlanner locale={locale} /></div></div></main>;
  if (key === "travel-tools") return <LocalizedTravelToolsPage locale={locale} />;
  if (key === "contact") return <HindiContact locale={locale} />;
  if (key.startsWith("kumbh-mela") || key.startsWith("char-dham-yatra") || key.startsWith("12-jyotirlinga")) return <LocalizedPilgrimagePage locale={locale} segments={slug} />;
  if (["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh", "kumbh-calendar"].includes(key)) return <KumbhGuidePage slug={key} locale={locale} />;
  const content = regionalPages[locale][key];
  if (!content) notFound();
  return <HindiPageTemplate content={content} locale={locale} />;
}

function LocalizedTravelToolsPage({ locale }: { locale: (typeof localeCodes)[number] }) {
  const copy = uiCopy[locale];
  return (
    <main>
      <section className="brand-gradient temple-silhouette pattern-mandala px-4 py-20 text-white sm:px-6 lg:px-8 lg:py-28">
        <div className="mx-auto max-w-7xl">
          <p className="inline-flex rounded-full border border-gold/40 bg-black/15 px-4 py-2 text-xs font-black uppercase tracking-[.18em] text-gold">{copy.planTrip}</p>
          <h1 className="mt-6 max-w-5xl font-serif text-5xl font-semibold leading-[1.05] sm:text-6xl lg:text-7xl">{copy.plannerTitle}</h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-orange-50/90 sm:text-xl">{copy.plannerDescription}</p>
        </div>
      </section>
      <section className="border-y border-amber-200 bg-amber-50 px-4 py-5 text-sm leading-7 text-amber-950 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">{copy.officialFirst}: {copy.notice}</div>
      </section>
      <section id="tools" className="bg-cream px-4 py-16 sm:px-6 lg:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <TravelSearchWidget title={copy.plannerTitle} sourcePage={`${locale}-travel-tools`} campaign="travel-tools" />
        </div>
      </section>
    </main>
  );
}
