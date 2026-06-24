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

type Props = { params: Promise<{ locale: string; slug: string[] }> };

export function generateStaticParams() {
  const slugs = [...Object.keys(regionalPages.hi), "plan-my-trip", "contact", "ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh", "kumbh-calendar"];
  return localeCodes.flatMap((locale) => slugs.map((slug) => ({ locale, slug: [slug] })));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale, slug } = await params;
  if (!isLocaleCode(locale)) return {};
  const key = slug.join("/");
  const copy = uiCopy[locale];
  const content = regionalPages[locale][key];
  const portalSlugs = ["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh", "kumbh-calendar"];
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
  if (key === "contact") return <HindiContact locale={locale} />;
  if (["ujjain-kumbh-2028", "nashik-kumbh-2027", "prayagraj-kumbh", "haridwar-kumbh", "kumbh-calendar"].includes(key)) return <KumbhGuidePage slug={key} locale={locale} />;
  const content = regionalPages[locale][key];
  if (!content) notFound();
  return <HindiPageTemplate content={content} locale={locale} />;
}
