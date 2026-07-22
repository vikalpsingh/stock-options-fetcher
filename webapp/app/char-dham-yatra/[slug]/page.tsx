import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { charDhamGuides, getCharDhamGuide } from "@/src/data/charDhamGuides";
import { HistoryStoriesPage, ItineraryPage, PackagesPage, PlaceGuidePage, RegistrationPage, SeniorGuidePage, ServicesPage, charDhamFaqs } from "@/src/components/pilgrimage/RichPilgrimagePages";
import { FAQSection, HowToReachSection, StayRecommendation } from "@/src/components/pilgrimage/PilgrimageTemplates";
import { VerificationNote } from "@/src/components/common/VerificationNote";

const sections = ["history", "registration", "route-map", "how-to-reach", "stay", "services", "senior-citizen-guide", "packages", "faqs"] as const;

export function generateStaticParams() {
  return [...charDhamGuides.map((site) => ({ slug: site.slug })), ...sections.map((slug) => ({ slug }))];
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const site = getCharDhamGuide(slug);
  const title = site ? `${site.templeName} | Char Dham Yatra Guide` : `Char Dham ${slug.replaceAll("-", " ")} | IndianKumbh.com`;
  return { title, description: site?.shortDescription || "Char Dham Yatra practical planning guide for families and senior citizens.", alternates: { canonical: `/char-dham-yatra/${slug}` }, keywords: site?.seoKeywords };
}

export default async function CharDhamSlugPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const site = getCharDhamGuide(slug);
  if (site) return <PlaceGuidePage pillar="char-dham" site={site} />;
  if (slug === "history") return <HistoryStoriesPage pillar="char-dham" />;
  if (slug === "registration") return <RegistrationPage />;
  if (slug === "route-map") return <ItineraryPage pillar="char-dham" />;
  if (slug === "services") return <ServicesPage pillar="char-dham" />;
  if (slug === "senior-citizen-guide") return <SeniorGuidePage pillar="char-dham" />;
  if (slug === "packages") return <PackagesPage pillar="char-dham" />;
  if (slug === "faqs") return <FAQSection faqs={charDhamFaqs} />;
  if (slug === "how-to-reach") return <main><HowToReachSection title="How to reach Char Dham Yatra" text="Most Char Dham plans start from Haridwar, Rishikesh, Dehradun or Delhi. Verify road status, weather and official traffic rules before travel." /><VerificationNote context="char-dham" /></main>;
  if (slug === "stay") return <main><StayRecommendation sourcePage="char-dham-stay" /><VerificationNote context="char-dham" /></main>;
  notFound();
}
