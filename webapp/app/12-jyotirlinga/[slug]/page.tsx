import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getJyotirlingaGuide, jyotirlingaGuides } from "@/src/data/jyotirlingaGuides";
import { HistoryStoriesPage, ItineraryPage, PackagesPage, PlaceGuidePage, SeniorGuidePage, ServicesPage, jyotirlingaFaqs } from "@/src/components/pilgrimage/RichPilgrimagePages";
import { FAQSection, HowToReachSection } from "@/src/components/pilgrimage/PilgrimageTemplates";
import { VerificationNote } from "@/src/components/common/VerificationNote";

const sections = ["history", "complete-itinerary", "how-to-reach", "services", "senior-citizen-guide", "senior-citizen-plan", "packages", "faqs"] as const;

export function generateStaticParams() {
  return [...jyotirlingaGuides.map((site) => ({ slug: site.slug })), ...sections.map((slug) => ({ slug }))];
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const site = getJyotirlingaGuide(slug);
  const title = site ? `${site.templeName} Travel Guide` : `12 Jyotirlinga ${slug.replaceAll("-", " ")} | IndianKumbh.com`;
  return { title, description: site?.shortDescription || "12 Jyotirlinga Darshan practical planning guide for families and senior citizens.", alternates: { canonical: `/12-jyotirlinga/${slug}` }, keywords: site?.seoKeywords };
}

export default async function JyotirlingaSlugPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const site = getJyotirlingaGuide(slug);
  if (site) return <PlaceGuidePage pillar="jyotirlinga" site={site} />;
  if (slug === "history") return <HistoryStoriesPage pillar="jyotirlinga" />;
  if (slug === "complete-itinerary") return <ItineraryPage pillar="jyotirlinga" />;
  if (slug === "services") return <ServicesPage pillar="jyotirlinga" />;
  if (slug === "senior-citizen-guide" || slug === "senior-citizen-plan") return <SeniorGuidePage pillar="jyotirlinga" />;
  if (slug === "packages") return <PackagesPage pillar="jyotirlinga" />;
  if (slug === "faqs") return <FAQSection faqs={jyotirlingaFaqs} />;
  if (slug === "how-to-reach") return <main><HowToReachSection title="How to reach the 12 Jyotirlingas" text="Plan Jyotirlinga travel by regional circuits: MP, Maharashtra, Gujarat, North, South and East. Verify temple timings and transport before booking." /><VerificationNote context="jyotirlinga" /></main>;
  notFound();
}
