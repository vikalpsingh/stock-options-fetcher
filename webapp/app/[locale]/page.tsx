import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { NationalKumbhHome } from "@/components/kumbh-portal";
import { isLocaleCode, localeCodes, type LocaleCode } from "@/lib/locale";
import { portalCopy } from "@/data/kumbh-portal";

type Props = { params: Promise<{ locale: string }> };

export function generateStaticParams() {
  return ["en", ...localeCodes].map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  if (!isLocaleCode(locale)) return {};
  const copy = portalCopy[locale];
  return {
    title: copy.heroTitle,
    description: copy.heroDescription,
    alternates: { canonical: `/${locale}`, languages: Object.fromEntries([["en", "/"], ...localeCodes.map((code) => [code, `/${code}`])]) },
    openGraph: { title: copy.heroTitle, description: copy.heroDescription, images: ["/images/mahakal-ghat-temple.png"] },
  };
}

export default async function LocalePage({ params }: Props) {
  const { locale } = await params;
  if (locale === "en") redirect("/");
  if (!isLocaleCode(locale)) notFound();
  return <NationalKumbhHome locale={locale as LocaleCode} />;
}
